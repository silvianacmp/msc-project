import argparse
import os
import pickle
import pprint

import numpy as np
import pandas as pd
import tensorflow as tf

from parsing.special_tokens import *
from path_rnn_v2.experiments.training import train_model
from path_rnn_v2.experiments.eval.evaluation import evaluate_model
from path_rnn_v2.experiments.prediction.prediction import generate_prediction
from path_rnn_v2.nn.textual_chains_of_reasoning_model import TextualChainsOfReasoningModel
from path_rnn_v2.util.batch_generator import PartitionBatchGenerator, ProportionedPartitionBatchGenerator
from path_rnn_v2.util.embeddings import RandomEmbeddings, Word2VecEmbeddings
from path_rnn_v2.util.tensor_generator import get_medhop_tensors

np.random.seed(0)


def max_entity_mentions(document_store):
    max = 0
    for doc_entities in document_store.document_entities:
        for pos in doc_entities.values():
            if len(pos) > max:
                max = len(pos)
    return max


# Instantiate the parser
parser = argparse.ArgumentParser()
parser.add_argument('--emb_dim',
                    type=int,
                    default=100,
                    help='Size of path-rnn embeddings')
parser.add_argument('--l2',
                    type=float,
                    default=0.0,
                    help='L2 loss regularization')
parser.add_argument('--dropout',
                    type=float,
                    default=0.0,
                    help='Path rnn dropout prob')
parser.add_argument('--paths_selection',
                    type=str,
                    default='shortest',
                    help='How the paths in the dataset were generated')
parser.add_argument('--tokenizer',
                    default='punkt',
                    help='Tokenizer used for the dataset')
parser.add_argument('--neighb_dim',
                    type=int,
                    default=3,
                    help='Entity neighborhood dimension')
parser.add_argument('--testing',
                    action='store_true',
                    help='If this is set, testing is run instead of training')
parser.add_argument('--predicting',
                    action='store_true',
                    help='If this is set, predicting is run instead of training')
parser.add_argument('--model_path',
                    default=None,
                    help='Model path if testing')
parser.add_argument('--eval_file_path',
                    default=None,
                    help='File to append evaluation results to')
parser.add_argument('--no_gpu_conf',
                    action='store_true',
                    help='If this is set, no gpu options will be passed in')
parser.add_argument('--word_embd_path',
                    type=str,
                    default='./medhop_word2vec_punkt_v2',
                    help='Word embedding path')

if __name__ == '__main__':
    # cmd line args
    args = parser.parse_args()
    no_gpu_conf = args.no_gpu_conf
    emb_dim = args.emb_dim
    l2 = args.l2
    dropout = args.dropout
    method = args.paths_selection
    tokenizer = args.tokenizer
    testing = args.testing
    predicting = args.predicting
    model_path = args.model_path
    eval_file_path = args.eval_file_path
    word_embd_path = args.word_embd_path
    neighb_dim = args.neighb_dim

    if not no_gpu_conf:
        os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"  # see issue #152
        os.environ["CUDA_VISIBLE_DEVICES"] = "0"
        config = tf.ConfigProto(gpu_options=tf.GPUOptions(visible_device_list='0',
                                                          per_process_gpu_memory_fraction=0.5))
    else:
        config = None

    limit = 100

    max_path_len = 5
    batch_size = 20
    num_epochs = 25

    path = './data'
    model_name = 'attention_truncated_relation_neighb'
    run_id_params = 'emb_dim={}_l2={}_drop={}_paths={}_tokenizer={}_balanced'.format(emb_dim, l2, dropout,
                                                                                     method, tokenizer)

    train = pd.read_json(
        '{}/sentwise=F_cutoff=4_limit={}_method={}_tokenizer={}_medhop_train.json'.format(path, limit, method,
                                                                                          tokenizer))
    train_document_store = pickle.load(open('{}/train_doc_store_{}.pickle'.format(path, tokenizer), 'rb'))

    dev = pd.read_json(
        '{}/sentwise=F_cutoff=4_limit={}_method={}_tokenizer={}_medhop_dev.json'.format(path, limit, method, tokenizer))
    dev_document_store = pickle.load(open('{}/dev_doc_store_{}.pickle'.format(path, tokenizer), 'rb'))

    if testing:
        test = pd.read_json(
            '{}/sentwise=F_cutoff=4_limit={}_method={}_tokenizer={}_medhop_test.json'.format(path, limit, method,
                                                                                             tokenizer))
        test_document_store = pickle.load(open('{}/test_doc_store_{}.pickle'.format(path, tokenizer), 'rb'))

    if predicting:
        test_no_label = pd.read_json(
            '{}/sentwise=F_cutoff=4_limit={}_method={}_tokenizer={}_medhop_test_mini_no_label.json'.format(path, limit,
                                                                                                           method,
                                                                                                           tokenizer))
        test_no_label_document_store = pickle.load(
            open('{}/test_mini_no_label_doc_store_{}.pickle'.format(path, tokenizer), 'rb'))

    max_ent_len = (2 * neighb_dim + 2) * \
                  max(max_entity_mentions(train_document_store), max_entity_mentions(dev_document_store))
    max_rel_len = max(train_document_store.max_tokens, dev_document_store.max_tokens)

    word2vec_embeddings = Word2VecEmbeddings(word_embd_path,
                                             name='token_embd',
                                             unk_token=UNK,
                                             trainable=False,
                                             special_tokens=[(ENT_1, False),
                                                             (ENT_2, False),
                                                             (ENT_X, False),
                                                             (UNK, False),
                                                             (END, False),
                                                             (NEIGHB_END, False),
                                                             (PAD, True)])
    target_embeddings = RandomEmbeddings(train['relation'],
                                         name='target_rel_emb',
                                         embedding_size=emb_dim,
                                         unk_token=None,
                                         initializer=tf.truncated_normal_initializer(mean=0.0,
                                                                                     stddev=1.0,
                                                                                     dtype=tf.float64))

    rel_retrieve_params = {
        'replacement': (ENT_1, ENT_2),
        'truncate': True
    }
    ent_retrieve_params = {
        'neighb_size': neighb_dim,
        'replacement': ENT_1,
        'end_token': NEIGHB_END
    }

    train_tensors = get_medhop_tensors(train['relation_paths'],
                                       train['entity_paths'],
                                       train['relation'],
                                       train['label'],
                                       train_document_store,
                                       word2vec_embeddings,
                                       word2vec_embeddings,
                                       target_embeddings,
                                       max_path_len=max_path_len,
                                       max_rel_len=max_rel_len,
                                       max_ent_len=max_ent_len,
                                       rel_retrieve_params=rel_retrieve_params,
                                       ent_retrieve_params=ent_retrieve_params)
    dev_tensors = get_medhop_tensors(dev['relation_paths'],
                                     dev['entity_paths'],
                                     dev['relation'],
                                     dev['label'],
                                     dev_document_store,
                                     word2vec_embeddings,
                                     word2vec_embeddings,
                                     target_embeddings,
                                     max_path_len=max_path_len,
                                     max_rel_len=max_rel_len,
                                     max_ent_len=max_ent_len,
                                     rel_retrieve_params=rel_retrieve_params,
                                     ent_retrieve_params=ent_retrieve_params)
    if testing:
        test_tensors = get_medhop_tensors(test['relation_paths'],
                                          test['entity_paths'],
                                          test['relation'],
                                          test['label'],
                                          test_document_store,
                                          word2vec_embeddings,
                                          word2vec_embeddings,
                                          target_embeddings,
                                          max_path_len=max_path_len,
                                          max_rel_len=max_rel_len,
                                          max_ent_len=max_ent_len,
                                          rel_retrieve_params=rel_retrieve_params,
                                          ent_retrieve_params=ent_retrieve_params)
    if predicting:
        prediction_tensors = get_medhop_tensors(test_no_label['relation_paths'],
                                                test_no_label['entity_paths'],
                                                test_no_label['relation'],
                                                None,
                                                test_no_label_document_store,
                                                word2vec_embeddings,
                                                word2vec_embeddings,
                                                target_embeddings,
                                                max_path_len=max_path_len,
                                                max_rel_len=max_rel_len,
                                                max_ent_len=max_ent_len,
                                                rel_retrieve_params=rel_retrieve_params,
                                                ent_retrieve_params=ent_retrieve_params)

    (rel_seq, ent_seq, path_len, rel_len, ent_len, target_rel, partition, label) = train_tensors

    pos = len(np.argwhere(label == 1))
    neg = len(np.argwhere(label == 0))
    positive_prop = float(pos) / neg

    train_batch_generator = ProportionedPartitionBatchGenerator(partition, label, batch_size=batch_size, permute=True,
                                                                positive_prop=positive_prop,
                                                                tensor_dict={'rel_seq': rel_seq,
                                                                             'ent_seq': ent_seq,
                                                                             'seq_len': path_len,
                                                                             'rel_len': rel_len,
                                                                             'ent_len': ent_len,
                                                                             'target_rel': target_rel})
    print('Positives per batch: {} \nNegatives per batch: {}'.format(train_batch_generator.positive_batch_size,
                                                                     train_batch_generator.negative_batch_size))
    train_eval_batch_generator = PartitionBatchGenerator(partition, label, batch_size=batch_size, permute=False,
                                                         tensor_dict={'rel_seq': rel_seq,
                                                                      'ent_seq': ent_seq,
                                                                      'seq_len': path_len,
                                                                      'rel_len': rel_len,
                                                                      'ent_len': ent_len,
                                                                      'target_rel': target_rel})
    (rel_seq, ent_seq, path_len, rel_len, ent_len, target_rel, partition, label) = dev_tensors
    dev_batch_generator = PartitionBatchGenerator(partition, label, batch_size=batch_size, permute=False,
                                                  tensor_dict={'rel_seq': rel_seq,
                                                               'ent_seq': ent_seq,
                                                               'seq_len': path_len,
                                                               'rel_len': rel_len,
                                                               'ent_len': ent_len,
                                                               'target_rel': target_rel})

    if testing:
        (rel_seq, ent_seq, path_len, rel_len, ent_len, target_rel, partition, label) = test_tensors
        test_batch_generator = PartitionBatchGenerator(partition, label, batch_size=batch_size, permute=False,
                                                       tensor_dict={'rel_seq': rel_seq,
                                                                    'ent_seq': ent_seq,
                                                                    'seq_len': path_len,
                                                                    'rel_len': rel_len,
                                                                    'ent_len': ent_len,
                                                                    'target_rel': target_rel})

    if predicting:
        (rel_seq, ent_seq, path_len, rel_len, ent_len, target_rel, partition) = prediction_tensors
        prediction_batch_generator = PartitionBatchGenerator(partition, label=None, batch_size=batch_size,
                                                             permute=False,
                                                             tensor_dict={'rel_seq': rel_seq,
                                                                          'ent_seq': ent_seq,
                                                                          'seq_len': path_len,
                                                                          'rel_len': rel_len,
                                                                          'ent_len': ent_len,
                                                                          'target_rel': target_rel})

    model_params = {
        'max_path_len': max_path_len,
        'max_rel_len': max_rel_len,
        'max_ent_len': max_ent_len,
        'relation_embedder': word2vec_embeddings,
        'relation_embedder_params': {
            'max_norm': None,
            'with_projection': True,
            'projection_activation': 'tanh',
            'projection_dim': None,
            'name': 'node_embedder',
            'reuse': False
        },
        'rel_encoder_name': 'node_encoder',
        'relation_encoder_params': {
            'module': 'additive_attention',
            'name': 'node_lstm_attention_encoder',
            'repr_dim': emb_dim,
            'activation': None,
            'dropout': None,
            'extra_args': {
                'with_backward': True,
                'with_projection': False
            }
        },
        'entity_embedder': word2vec_embeddings,
        'entity_embedder_params': {
            'max_norm': None,
            'with_projection': True,
            'projection_activation': 'tanh',
            'projection_dim': None,
            'name': 'node_embedder',
            'reuse': True
        },
        'ent_encoder_name': 'node_encoder',
        'entity_encoder_params': {
            'module': 'additive_attention',
            'name': 'node_lstm_attention_encoder',
            'repr_dim': emb_dim,
            'activation': None,
            'dropout': None,
            'extra_args': {
                'with_backward': True,
                'with_projection': False
            }
        },
        'target_embedder': target_embeddings,
        'target_embedder_params': {
            'max_norm': None,
            'with_projection': True,
            'projection_activation': 'tanh',
            'projection_dim': None,
            'name': 'target_relation_embedder',
            'reuse': False
        },
        'path_encoder_params': {
            'repr_dim': emb_dim,
            'module': 'lstm',
            'name': 'path_encoder',
            'activation': None,
            'dropout': dropout,
            'extra_args': {
                'with_backward': False,
                'with_projection': False
            }
        },
        'path_rnn_params': {
            'aggregator': 'logsumexp',
            'k': None
        }
    }

    train_params = {
        'optimizer': tf.train.AdamOptimizer(learning_rate=1e-3),
        'l2': l2,
        'clip_op': None,
        'clip': None
    }

    model = TextualChainsOfReasoningModel(model_params, train_params)
    print(model.params_str)
    print(pprint.pformat(model.train_variables))

    if not testing and not predicting:
        train_model(model, train=train, train_batch_generator=train_batch_generator,
                    train_eval_batch_generator=train_eval_batch_generator,
                    dev=dev, dev_batch_generator=dev_batch_generator, model_name=model_name,
                    run_id_params=run_id_params,
                    num_epochs=num_epochs, config=config, check_period=50)
    elif not predicting:
        word_embd = word2vec_embeddings.embed_sequence(seq=None, name='node_embedder', max_norm=None,
                                                       with_projection=True,
                                                       projection_activation='tanh',
                                                       projection_dim=None, reuse=True)
        evaluate_model(model, model_path=model_path, train=train, train_eval_batch_generator=train_eval_batch_generator,
                       dev=dev, dev_batch_generator=dev_batch_generator, test=test,
                       test_batch_generator=test_batch_generator, eval_file_path=eval_file_path, word_embd=word_embd)
    else:
        generate_prediction(model, model_path=model_path, test=test_no_label,
                            test_batch_generator=prediction_batch_generator, eval_file_path=eval_file_path)