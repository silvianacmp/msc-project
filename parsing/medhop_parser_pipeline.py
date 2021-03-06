import argparse
import json
import pickle

import numpy as np
import pandas as pd

from parsing.genia.word_tokenize import GTBTokenizer
from nltk.tokenize import TreebankWordTokenizer, WordPunctTokenizer
from parsing.medhop_graph_extraction import preprocess_medhop
from parsing.medhop_path_extraction import extract_paths_dataset, extract_source_target_dataset
from parsing.sent_tokenize import NLTKSentTokenizer, GeniaSentTokenizer

np.random.seed(0)

tokenizer = {
    'punkt': WordPunctTokenizer(),
    'treebank': TreebankWordTokenizer(),
    'genia': GTBTokenizer()
}

sent_tokenizer = {
    'nltk': NLTKSentTokenizer(),
    'genia': GeniaSentTokenizer()
}

# Instantiate the parser
parser = argparse.ArgumentParser(description='Optional app description')
parser.add_argument('input_path',
                    type=str,
                    help='Dataset path')

parser.add_argument('output_path',
                    type=str,
                    help='Output path')

parser.add_argument('document_store_path',
                    type=str,
                    help='Document store path')
parser.add_argument('--sentence_wise',
                    action='store_true',
                    help='If this is set, the paths will be between entities in the same sentence.')
parser.add_argument('--masked',
                    action='store_true',
                    help='If this is set, masks will also be matched as entities.')
parser.add_argument('--entities_path',
                    type=str,
                    default=None,
                    help='Path to list of entities to be extracted')
parser.add_argument('--path_search_method',
                    type=str,
                    default='all',
                    help='One of all, shortest, shortest_plus.')
parser.add_argument('--cutoff',
                    type=int,
                    default=4,
                    help='Max length of paths to be considered')
parser.add_argument('--limit',
                    type=int,
                    default=500,
                    help='Max number of paths per query')
parser.add_argument('--tokenizer',
                    type=str,
                    default='punkt',
                    help='One of punkt or treebank or genia')
parser.add_argument('--sent_tokenizer',
                    type=str,
                    default='nltk',
                    help='One of nltk, genia')
parser.add_argument('--stupid_dataset',
                    action='store_true',
                    help='If set it will generate a dumb dataset with only the source and target on the chain')

print('Start')
args = parser.parse_args()
print('Input path:{}\n'
      'Output path:{}\n'
      'Document store path:{}\n'
      'Entities path:{}\n'
      'Sentence wise:{}\n'
      'Path search method:{}\n'
      'Cutoff:{}\n'
      'Limit:{}\n'
      'Tokenizer:{}\n'
      'Sent tokenizer: {}\n'
      'Masked: {}\n'
      'Stupid dataset: {}\n'.format(args.input_path,
                              args.output_path,
                              args.document_store_path,
                              args.entities_path,
                              args.sentence_wise,
                              args.path_search_method,
                              args.cutoff,
                              args.limit,
                              args.tokenizer,
                              args.sent_tokenizer,
                              args.masked,
                              args.stupid_dataset), flush=True)

df = pd.read_json(args.input_path, orient='records')
df, document_store = preprocess_medhop(df,
                                       sentence_wise=args.sentence_wise,
                                       entity_list_path=args.entities_path,
                                       word_tokenizer=tokenizer[args.tokenizer],
                                       sent_tokenizer=sent_tokenizer[args.sent_tokenizer],
                                       allow_masks=args.masked,
                                       skip_graph=args.stupid_dataset
                                       )
if not args.stupid_dataset:
    paths_dataset = extract_paths_dataset(df,
                                          path_search_method_name=args.path_search_method,
                                          cutoff=args.cutoff,
                                          limit=args.limit
                                          )
else:
    paths_dataset = extract_source_target_dataset(df)

if not args.stupid_dataset:
    pickle.dump(document_store, open(args.document_store_path, 'wb'))
with open(args.output_path, "w") as text_file:
    text_file.write(json.dumps(paths_dataset))
