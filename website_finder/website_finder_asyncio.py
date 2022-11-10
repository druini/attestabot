from glob import glob
import pandas as pd
import asyncio, aiohttp
import multiprocessing
import os
from datetime import datetime
from UrlMaker import UrlMaker
from pdb import set_trace


def now():
    return datetime.strftime(datetime.now(), "%H:%M:%S")

async def check_urls_task(url, idx, session):
    status_is_200 = False
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=5)) as response:
            if response.status==200:
                status_is_200 = True
    except:
        pass
    return (idx,status_is_200)


async def bound_check_urls_task(semaphore, url, idx, session):
    async with semaphore:
        return await check_urls_task(url, idx, session)


async def check_urls_kernel(df):
    rows_to_check = (df.url_exists.isna())
    sem = asyncio.Semaphore(5000)
    async with aiohttp.ClientSession() as session:
        tasks = []
        for idx,firm in df[rows_to_check].iterrows():
            task = asyncio.ensure_future(bound_check_urls_task(sem, firm['url'], idx, session))
            tasks.append(task)
        print(f'{now()} {df.iloc[0].canton} launched all asyncio tasks')
        return await asyncio.gather(*tasks, return_exceptions=True)


def check_urls(pkl_file, df):
    today = datetime.strftime(datetime.now(), '%Y-%m-%d')
    valid_urls = asyncio.run(check_urls_kernel(df))
    print(f'{now()} {os.path.basename(pkl_file)} asyncio finished, writing results to df')
    for idx,url_exists in valid_urls:
        df.iloc[int(idx)]['url_exists'] = str(url_exists).upper()
        df.iloc[int(idx)]['url_checked_on'] = today
    print(f'{now()} {os.path.basename(pkl_file)} saving files')
    df.to_pickle( pkl_file )
    df.to_excel( pkl_file.replace('.pkl', '.xlsx') )
    del df
    print(f'{now()} closing {pkl_file}')


def add_urls_to_dataframe_kernel(df):
    url_maker = UrlMaker()
    new_rows  = []
    for url in url_maker.make_urls(df.iloc[0]['name']):
        if url not in df.url.values:
            new_row = df.iloc[0].copy()
            new_row.url = url
            new_row.url_exists = None
            new_row.url_checked_on = None
            new_rows.append(new_row.to_frame().T)
    return pd.concat(new_rows)


def add_urls_to_dataframe(df):
    if 'url' not in df.columns:
        for new_column in ('url', 'url_exists', 'url_checked_on'):
            df[new_column] = pd.Series([None for _ in range(len(df.index))])

    with multiprocessing.Pool() as pool:
        all_new_rows = pool.map(add_urls_to_dataframe_kernel, (df.query('name==@name') for name in set(df['name'])))
    df = pd.concat([df.dropna(subset='url'), *all_new_rows])
    df.sort_values(by='name', ignore_index=True, inplace=True)
    print(f'{now()} added rows for urls')
    return df


def main():
    files = glob( os.path.join('..', 'firms','firms*pkl') )
    canton_firms = {}
    for pkl_file in files:
        df = pd.read_pickle(pkl_file)
        print(f'{now()} loading {pkl_file}, with {len(set(df["name"]))} firms')
        df = add_urls_to_dataframe(df)
        df.to_pickle( pkl_file )
        df.to_excel( pkl_file.replace('.pkl', '.xlsx') )
        canton_firms[pkl_file] = df.copy()
    with multiprocessing.Pool() as pool:
        pool.starmap(check_urls, canton_firms.items())


if __name__=='__main__':
    main()