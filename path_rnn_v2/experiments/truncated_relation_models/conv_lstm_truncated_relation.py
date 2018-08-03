import numpy as np

from parsing.special_tokens import *
from path_rnn_v2.experiments.experiment_base import run_model

np.random.seed(0)


def model_params_generator(max_path_len, max_rel_len, max_ent_len, word2vec_embeddings, target_embeddings, emb_dim,
                           dropout, args):
    return {
        'max_path_len': max_path_len,
        'max_rel_len': max_rel_len,
        'rel_only': True,
        'relation_embedder': word2vec_embeddings,
        'relation_embedder_params': {
            'max_norm': None,
            'with_projection': True,
            'projection_activation': 'tanh',
            'projection_dim': None,
            'name': 'node_embedder',
            'reuse': False
        },
        'relation_encoder_params': {
            'module': 'conv_lstm',
            'name': 'relation_conv_lstm_encoder',
            'repr_dim': emb_dim,
            'activation': None,
            'dropout': None,
            'extra_args': {
                'conv_activation': 'relu',
                'conv_out_channels': args.conv_out_channels,
                'conv_width': args.conv_width,
                'lstm_with_projection': False,
                'lstm_with_backward': True,
                'lstm_last_output': True
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


def extra_parser_args_adder(parser):
    parser.add_argument('--conv_width',
                        type=int,
                        default=5,
                        help='Width of the convolutional filters')
    parser.add_argument('--conv_out_channels',
                        type=int,
                        default=100,
                        help='Number of channels after apply the conv op')


if __name__ == '__main__':
    visible_device_list = '0'
    visible_devices = '1'
    memory_fraction = 0.5

    model_name = 'conv_lstm_truncated_relation'
    extra_args_formatter = lambda args: 'conv_width={}_conv_channels={}'.format(args.conv_width, args.conv_out_channels)
    max_ent_len_retrieve = lambda train_doc_store, dev_doc_store, args: 1
    max_rel_len_retrieve = lambda train_doc_store, dev_doc_store, args: max(train_doc_store.max_tokens,
                                                                            dev_doc_store.max_tokens)
    rel_retrieve_params = {
        'replacement': (ENT_1, ENT_2),
        'truncate': True
    }
    ent_retrieve_params = {}
    tensor_dict_map = {'rel_seq': 'rel_seq',
                       'seq_len': 'seq_len',
                       'rel_len': 'rel_len',
                       'target_rel': 'target_rel'}
    run_model(visible_device_list=visible_device_list, visible_devices=visible_devices,
              memory_fraction=memory_fraction, model_name=model_name, extra_parser_args_adder=extra_parser_args_adder,
              extra_args_formatter=extra_args_formatter, max_ent_len_retrieve=max_ent_len_retrieve,
              max_rel_len_retrieve=max_rel_len_retrieve, rel_retrieve_params=rel_retrieve_params,
              ent_retrieve_params=ent_retrieve_params, tensor_dict_map=tensor_dict_map,
              model_params_generator=model_params_generator, no_save=True)