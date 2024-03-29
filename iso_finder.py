from glob import glob
import pandas as pd
import sys, os, logging, jsonlines, multiprocessing
from datetime import datetime
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from attestabot.spiders.IsoFinder import IsoFinder
from pdb import set_trace

OUTFILE_RAW   = 'iso_finder_raw.jl'
#INPUT_FOLDER  = 'firms_website_finder'
INPUT_FOLDER  = 'firms_moneyhouse'
OUTPUT_FOLDER = 'firms_iso_finder'
LOGFILE       = 'iso_finder.log'

def sort_dataframes_and_save(parquet_infile, outfile_raw):
    df_moneyhouse = pd.read_parquet(parquet_infile)
    df_moneyhouse = df_moneyhouse[df_moneyhouse.homepage.notna()]
    with jsonlines.open(outfile_raw) as jl_file:
        rows = (pd.Series(row) for row in jl_file if row['parquet_file']==parquet_infile)
        df_iso_finder = pd.concat(rows, axis=1).T.drop(columns='parquet_file')
    df_moneyhouse['iso_finder_checked_on'] = df_iso_finder.iloc[0]['iso_finder_checked_on']
    df_moneyhouse['has_iso_info'] = 'FALSE'
    for i in range(1,4):
        df_moneyhouse[f'found_iso_{i}'] = 'FALSE'
    for idx in df_moneyhouse.index:
        subdf_iso_finder = df_iso_finder.query('df_index==@idx').sort_values(by=['suburl_is_iso_file','suburl_has_logo','suburl_has_keyword'], ascending=False)[:3]
        if len(subdf_iso_finder)>0:
            df_moneyhouse.loc[idx, 'has_iso_info'] = 'TRUE'
            for i, (_, row) in enumerate(subdf_iso_finder.iterrows(), start=1):
                df_moneyhouse.loc[idx, f'found_iso_{i}'] = row.suburl_with_iso_info

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    outfile = os.path.basename(parquet_infile)
    outfile = os.path.join(OUTPUT_FOLDER, outfile)
    df_moneyhouse.to_parquet( outfile )
    df_moneyhouse.to_excel( outfile.replace('.parquet','.xlsx') )
    del df_moneyhouse, df_iso_finder


def crawler_func(files):
    suffix = 1 if 'firms_FR.parquet' in files else 2
    outfile = OUTFILE_RAW.replace('.jl',f'_{suffix}.jl')
    files = [os.path.join(INPUT_FOLDER, parquet_file) for parquet_file in files]
    crawler_settings = get_project_settings()
    #crawler_settings['LOG_FILE']             = LOGFILE.replace('.log',f'_{suffix}.log')
    crawler_settings['LOG_ENABLED']          = True
    #crawler_settings['LOG_FILE_APPEND']      = False
    crawler_settings['LOG_LEVEL']            = 'INFO'
    #crawler_settings['LOG_LEVEL']            = 'DEBUG'
    crawler_settings['FEEDS']                = {
            outfile : {'format': 'jsonlines'}
            }

    crawler_process = CrawlerProcess(crawler_settings)
    for parquet_file in files:
        crawler_process.crawl(IsoFinder, parquet_file=parquet_file)

    logging.info(f'Starting crawl jobs')
    crawler_process.start()

    logging.info(f'Done crawling part {suffix}, will now write raw results to Excel files')

    for parquet_infile in files:
        sort_dataframes_and_save(parquet_infile, outfile)
    #with multiprocessing.Pool() as pool:
    #    pool.map(sort_dataframes_and_save, files)
    logging.info(f'finished part {suffix}')


def main():
    files_1 = [
            'firms_FR.parquet',
            'firms_NW.parquet',
            'firms_GE.parquet',
            'firms_AR.parquet',
            'firms_TI.parquet',
            'firms_VS_Central.parquet',
            'firms_VD.parquet',
            'firms_BE.parquet',
            'firms_TG.parquet',
            'firms_BL.parquet',
            'firms_UR.parquet',
            'firms_GR.parquet',
            'firms_GL.parquet',
            'firms_SG.parquet'
            ]
    files_2 = [
            'firms_BS.parquet',
            'firms_OW.parquet',
            'firms_ZH.parquet',
            'firms_AG.parquet',
            'firms_AI.parquet',
            'firms_ZG.parquet',
            'firms_SH.parquet',
            'firms_VS_Bas.parquet',
            'firms_LU.parquet',
            'firms_SO.parquet',
            'firms_VS_Ober.parquet',
            'firms_SZ.parquet',
            'firms_JU.parquet',
            'firms_NE.parquet'
            ]

    with multiprocessing.Pool() as pool:
        pool.map(crawler_func, [files_1, files_2])

    logging.info('all done')


if __name__=='__main__':
    main()
