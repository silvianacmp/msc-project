#!/usr/bin/env bash
for lim in 100
do
  for tok in genia punkt
  do
    for type in test_mini_no_label
    do
      for method in shortest
      do
        if [ ${tok} = "genia" ];
        then
          sent_tok=genia
        else
          sent_tok=nltk
        fi

        echo "${type} ${lim} ${tok} ${sent_tok} ${method}"
          PYTHONPATH=../ python -u \
                ../parsing/medhop_parser_pipeline.py \
                "../qangaroo_v1.1/medhop/${type}.json" \
                "../data/sentwise=F_cutoff=4_limit=${lim}_method=${method}_tokenizer=${tok}_medhop_${type}.json" \
                "../data/${type}_doc_store_${tok}.pickle" \
                --limit=${lim} \
                --cutoff=4 \
                --entities_path='./entities.txt' \
                --path_search_method=${method} \
                --tokenizer=${tok} \
                --sent_tokenizer=${sent_tok}
      done
    done
  done
done
