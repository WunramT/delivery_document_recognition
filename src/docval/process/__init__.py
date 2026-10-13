"""Production process for one scanned tour (`make process`, `make finalize`).

scan -> per page: doc type, objects, tour number, CMR count, TA numbers (run.py)
     -> organisational checks, automatic (organize.py)
     -> review page: a person confirms every signature/stamp result (review.py)
     -> decision file -> sorted PDFs, e-mail drafts, protocol (finalize.py)
"""
