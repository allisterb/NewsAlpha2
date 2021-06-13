"""CLI interface for NewsAlpha"""

import os
import sys
import threading
import argparse
import warnings
import logging
from logging import info, error, debug, warn
import kbinput
from pathlib import Path
import psycopg2
from pyfiglet import Figlet

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

SOURCES = [
    'abcnews.go.com',
    'www.alternet.org',
    'apnews.com',
    'www.axios.com',
    'www.bbc.com',
    'www.bloomberg.com',
    'www.breitbart.com',
    'buzzfeednews.com',
    'www.cbsnews.com',
    'www.csmonitor.com',
    'www.cnn.com',
    'www.thedailybeast.com',
    'dailymail.co.uk',
    'www.democracynow.org'
]
def print_logo():
    """Print program logo."""
    fig = Figlet(font='chunky')
    print(fig.renderText('NewsAlpha') + 'v0.1\n')
    
parser = argparse.ArgumentParser()
parser.add_argument("--debug", help="Enable debug-level logging.", action="store_true")
parser.add_argument("--host", help="Server host where the NewsAlpha PGSQL database is located.", default='127.0.0.1')
parser.add_argument("--port", help="PGSQL server database port.", default='5432')
parser.add_argument("--data", help="Set the data import directory if needed.")
parser.add_argument("--args", help="Additional arguments comma-delimited as key=value e.g --args \'ppm=4,fps=1\'")
parser.add_argument("--importarticles", help="Import article data from data folder into database.", action='store_true')
args = parser.parse_args()

if args.debug:
    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%I:%M:%S %p', level=logging.DEBUG)
    info("Debug mode enabled.")
else:
    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%I:%M:%S %p', level=logging.INFO)

print_logo()
threading.Thread(target=kbinput.kb_capture_thread, args=(), name='kb_capture_thread', daemon=True).start()

custom_args = {}
if args.args is not None:
    for a in args.args.split(','):
        kv = a.split('=')
        if len(kv) != 2:
            error(f'The argument {kv} is malformed.')
            sys.exit(1)
        k, v = kv[0], kv[1]
        custom_args[k] = v
    debug(f'Custom arguments are {custom_args}.')
password = os.environ.get('NA_PASSWORD', 'newsalpha')
try:
    with psycopg2.connect(f'host={args.host} port={args.port} dbname=newsalpha user=newsalpha password={password}') as c:
        info(f'Connection to PGSQL database at {args.host}:{args.port} with user newsalpha OK.')
except psycopg2.OperationalError as oe:
    error(f'Could not connect to PGSQL database at {args.host}:{args.port} with user newsalpha.')
    error(oe)
    sys.exit(1)

if args.importarticles:
    if not args.data:
        error("The import data directory is not specified.")
        sys.exit(1)
    elif not(Path(args.data).exists() or Path(args.data).is_dir()):
        error(f'The path {args.data} does not exists or is not a directory.')
        sys.exit(1)
    files = os.listdir(args.data)
    file_count = len(files) 
    info(f'{file_count} files to import article data from in {args.data}. Press ENTER to stop article import.')
    from urllib.parse import urlparse
    from warcio.archiveiterator import ArchiveIterator
    from newspaper import Article
    cf = 0
    with psycopg2.connect(f'host={args.host} port={args.port} dbname=newsalpha user=newsalpha password={password}') as conn:
        curr = conn.cursor()
        ins_stmt = "INSERT INTO news_articles (source, lang, url, title, text) VALUES (%s, %s, %s, %s, %s)"
        while (file_count > 0 and not kbinput.KBINPUT):
            articles_processed = 0
            articles_skipped = 0
            file = os.path.join(args.data, files[cf])
            with open(file, 'rb') as f:
                info(f'Processing file {file}...')
                a = ArchiveIterator(f)
                for r in ArchiveIterator(f):
                    if kbinput.KBINPUT: 
                        info('Stopping...')
                        break
                    if r.rec_type == 'response' and r.http_headers.get_header('Content-Type') == 'text/html' and r.raw_stream.limit > 0:
                        url = r.rec_headers['WARC-Target-URI']
                        host = urlparse(url).netloc
                        article = Article('')
                        article.download(input_html=r.content_stream().read())
                        article.parse()
                        if article.meta_lang == 'en' and article.title != '' and article.title != '':
                            info(article.top_image)
                            articles_processed += 1
                        else:
                            warn(f'Skipping {url} with no title or (en) text.')
                            articles_skipped += 1
                cf += 1
                file_count -= 1