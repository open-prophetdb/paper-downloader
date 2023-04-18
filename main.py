import os
import re
import click
import requests
import logging
import coloredlogs
import verboselogs
import time
import json
import hashlib
import csv
import datetime
import subprocess
from tqdm import tqdm
from metapub import PubMedFetcher
from lxml import etree
from bs4 import BeautifulSoup
import urllib3
from metapub import PubMedFetcher
from retrying import retry

# log config
logging.basicConfig()
logger = logging.getLogger('Sci-Hub')
logger.setLevel(logging.DEBUG)

#
urllib3.disable_warnings()

# constants
SCHOLARS_BASE_URL = 'https://scholar.google.com/scholar'
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:27.0) Gecko/20100101 Firefox/27.0'}

verboselogs.install()
coloredlogs.install(
    fmt='%(asctime)s - %(module)s:%(lineno)d - %(levelname)s - %(message)s')
logger = logging.getLogger('root')
logging.root.setLevel(logging.NOTSET)

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
}


def read_file_as_text(text_file):
    with open(text_file, 'r') as f:
        return f.read()


def read_css_file(file):
    """Read the CSS contents from a file."""
    css_path = os.path.join(os.path.dirname(__file__), 'css', file)
    with open(css_path, 'r') as css_file:
        return css_file.read()


verboselogs.install()
coloredlogs.install(
    fmt='%(asctime)s - %(module)s:%(lineno)d - %(levelname)s - %(message)s')
logger = logging.getLogger('root')
logging.root.setLevel(logging.NOTSET)

headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
}

def embed_styles(html_file):
    if os.path.exists(html_file):
        text = read_file_as_text(html_file)
        soup = BeautifulSoup(text, 'html.parser')
        css = read_css_file('pdf.css')

        # Create a new `style` element and insert the CSS contents
        style_tag = soup.new_tag('style')
        style_tag.string = css
        soup.head.append(style_tag)
        with open(html_file, 'w') as f:
            f.write(str(soup))
    else:
        logger.warning("No such html file (%s), please check it." % html_file)


def write_csv(data, filename):
    headers = data[0].keys()
    with open(filename, 'w', newline='') as myfile:
        writer = csv.DictWriter(myfile, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)


def write_json(data, filename):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)


def read_json(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return json.load(f)
    else:
        return []
    

class SciHub(object):
    """
    SciHub class can search for papers on Google Scholars 
    and fetch/download papers from sci-hub.io
    """

    def __init__(self):
        self.sess = requests.Session()
        self.sess.headers = HEADERS
        self.available_base_url_list = self._get_available_scihub_urls()
        self.base_url = self.available_base_url_list[0] + '/'

    def _get_available_scihub_urls(self):
        '''
        Finds available scihub urls via https://sci-hub.now.sh/
        '''
        return ["https://sci-hub.ee", "https://sci-hub.ru", "https://sci-hub.se"]
        urls = []
        res = requests.get('https://sci-hub.now.sh/')
        s = self._get_soup(res.content)
        for a in s.find_all('a', href=True):
            if 'sci-hub.' in a['href']:
                urls.append(a['href'])
        return urls

    def set_proxy(self, proxy):
        '''
        set proxy for session
        :param proxy_dict:
        :return:
        '''
        if proxy:
            self.sess.proxies = {
                "http": proxy,
                "https": proxy, }

    def _change_base_url(self):
        if not self.available_base_url_list:
            raise Exception('Ran out of valid sci-hub urls')
        del self.available_base_url_list[0]
        self.base_url = self.available_base_url_list[0] + '/'
        logger.info("I'm changing to {}".format(self.available_base_url_list[0]))

    def search(self, query, limit=10, download=False):
        """
        Performs a query on scholar.google.com, and returns a dictionary
        of results in the form {'papers': ...}. Unfortunately, as of now,
        captchas can potentially prevent searches after a certain limit.
        """
        start = 0
        results = {'papers': []}

        while True:
            try:
                res = self.sess.get(SCHOLARS_BASE_URL, params={'q': query, 'start': start})
            except requests.exceptions.RequestException as e:
                results['err'] = 'Failed to complete search with query %s (connection error)' % query
                return results

            s = self._get_soup(res.content)
            papers = s.find_all('div', class_="gs_r")

            if not papers:
                if 'CAPTCHA' in str(res.content):
                    results['err'] = 'Failed to complete search with query %s (captcha)' % query
                return results

            for paper in papers:
                if not paper.find('table'):
                    source = None
                    pdf = paper.find('div', class_='gs_ggs gs_fl')
                    link = paper.find('h3', class_='gs_rt')

                    if pdf:
                        source = pdf.find('a')['href']
                    elif link.find('a'):
                        source = link.find('a')['href']
                    else:
                        continue

                    results['papers'].append({
                        'name': link.text,
                        'url': source
                    })

                    if len(results['papers']) >= limit:
                        return results

            start += 10

    @retry(wait_random_min=100, wait_random_max=1000, stop_max_attempt_number=10)
    def download(self, identifier, destination='', path=None):
        """
        Downloads a paper from sci-hub given an indentifier (DOI, PMID, URL).
        Currently, this can potentially be blocked by a captcha if a certain
        limit has been reached.
        """
        data = self.fetch(identifier)

        if not 'err' in data:
            self._save(data['pdf'],
                       os.path.join(destination, path if path else data['name']))

        return data

    def fetch(self, identifier):
        """
        Fetches the paper by first retrieving the direct link to the pdf.
        If the indentifier is a DOI, PMID, or URL pay-wall, then use Sci-Hub
        to access and download paper. Otherwise, just download paper directly.
        """

        try:
            url = self._get_direct_url(identifier)
            logger.info('Resolved url %s for identifier %s' % (url, identifier))

            # verify=False is dangerous but sci-hub.io 
            # requires intermediate certificates to verify
            # and requests doesn't know how to download them.
            # as a hacky fix, you can add them to your store
            # and verifying would work. will fix this later.
            res = self.sess.get(url, verify=False)

            if res.headers['Content-Type'] != 'application/pdf':
                self._change_base_url()
                logger.info('Failed to fetch pdf with identifier %s '
                                           '(resolved url %s) due to captcha' % (identifier, url))
                raise CaptchaNeedException('Failed to fetch pdf with identifier %s '
                                           '(resolved url %s) due to captcha' % (identifier, url))
                # return {
                #     'err': 'Failed to fetch pdf with identifier %s (resolved url %s) due to captcha'
                #            % (identifier, url)
                # }
            else:
                return {
                    'pdf': res.content,
                    'url': url,
                    'name': self._generate_name(res)
                }

        except requests.exceptions.ConnectionError:
            logger.info('Cannot access {}, changing url'.format(self.available_base_url_list[0]))
            self._change_base_url()

        except requests.exceptions.RequestException as e:
            logger.info('Failed to fetch pdf with identifier %s (resolved url %s) due to request exception.'
                       % (identifier, url))
            return {
                'err': 'Failed to fetch pdf with identifier %s (resolved url %s) due to request exception.'
                       % (identifier, url)
            }

    def _get_direct_url(self, identifier):
        """
        Finds the direct source url for a given identifier.
        """
        id_type = self._classify(identifier)

        return identifier if id_type == 'url-direct' \
            else self._search_direct_url(identifier)

    def _search_direct_url(self, identifier):
        """
        Sci-Hub embeds papers in an iframe. This function finds the actual
        source url which looks something like https://moscow.sci-hub.io/.../....pdf.
        """
        res = self.sess.get(self.base_url + identifier, verify=False)
        logger.info('Getting direct url %s' % self.base_url + identifier)
        s = self._get_soup(res.content)
        iframe = s.find('iframe')
        if iframe:
            return iframe.get('src') if not iframe.get('src').startswith('//') \
                else 'http:' + iframe.get('src')

    def _classify(self, identifier):
        """
        Classify the type of identifier:
        url-direct - openly accessible paper
        url-non-direct - pay-walled paper
        pmid - PubMed ID
        doi - digital object identifier
        """
        if (identifier.startswith('http') or identifier.startswith('https')):
            if identifier.endswith('pdf'):
                return 'url-direct'
            else:
                return 'url-non-direct'
        elif identifier.isdigit():
            return 'pmid'
        else:
            return 'doi'

    def _save(self, data, path):
        """
        Save a file give data and a path.
        """
        with open(path, 'wb') as f:
            f.write(data)

    def _get_soup(self, html):
        """
        Return html soup.
        """
        return BeautifulSoup(html, 'html.parser')

    def _generate_name(self, res):
        """
        Generate unique filename for paper. Returns a name by calcuating 
        md5 hash of file contents, then appending the last 20 characters
        of the url which typically provides a good paper identifier.
        """
        name = res.url.split('/')[-1]
        name = re.sub('#view=(.+)', '', name)
        pdf_hash = hashlib.md5(res.content).hexdigest()
        return '%s-%s' % (pdf_hash, name[-20:])



class PubMed(PubMedFetcher):
    """Get articles from pubmed.

    Steps:
        pubmed = PubMed()
        pubmed.batch_query_pmids(query_str)
        pubmed.remove_dup_pmids(files)
        pubmed.fetch_save_metadata()
    """

    def __init__(self, method='eutils', cachedir='.cache', delay=1, dest_file="."):
        self.counts = 0
        self.delay = delay
        self.pmids = []
        self.metadata = []
        self.dest_file = dest_file

        if os.path.exists(dest_file):
            raise Exception(
                "%s does exist, please delete it and retry." % dest_file)

        super().__init__(method, cachedir)

    def _count(self, query_str):
        result = self.qs.esearch({'db': 'pubmed', 'term': query_str,
                                  'rettype': 'count', 'retmax': 250,
                                 'retstart': 0})
        return (int(etree.fromstring(result).find('Count').text.strip()))

    def batch_query_pmids(self, query_str):
        logger.info("Fetch the metadata with query_str (%s)..." % query_str)
        pmids = []
        self.counts = self._count(query_str)
        for i in range(0, (self.counts // 250) + 1):
            time.sleep(self.delay)
            r = self.pmids_for_query(query_str, retmax=250, retstart=i * 250)
            logger.info("Fetch the first %s articles" % len(r))
            pmids.extend(r)
        self.pmids = pmids
        logger.info("Get %s papers" % len(pmids))

    def remove_dup_pmids(self, files):
        logger.info("Remove the duplicated articles...")
        for file in files:
            try:
                articles = read_json(file)
                if type(articles) == list and len(articles) > 0:
                    pmids = [str(article.get("pmid"))
                             for article in articles if article.get("pmid")]
                    total = len(self.pmids)
                    self.pmids = [
                        pmid for pmid in self.pmids if pmid not in pmids]
                    logger.info("Find %s duplicated pmids and %s unique pmids" %
                                ((total - len(self.pmids)), len(self.pmids)))
            except Exception as e:
                logger.error("Load %s error, reason: %s" % (file, e))

    def fetch_save_metadata(self):
        logger.info("Fetch the metadata for articles...")
        pbar = tqdm(self.pmids)
        year = datetime.datetime.now().year
        for pmid in pbar:
            paper = {}
            article = self.article_by_pmid(pmid)
            paper["pmid"] = int(pmid)
            paper["pmcid"] = article.pmc if article.pmc else ''
            paper["pmc_link"] = 'https://www.ncbi.nlm.nih.gov/pmc/articles/' + \
                article.pmc if article.pmc else ''
            paper["pubmed_link"] = 'https://pubmed.ncbi.nlm.nih.gov/' + pmid
            paper["abstract"] = article.abstract.replace(
                "\n", " ") if article.abstract is not None else ''
            paper["title"] = article.title
            paper["authors"] = ', '.join(article.authors)
            paper["journal"] = article.journal
            paper["publication"] = article.year
            paper["publication_link"] = 'https://publications.3steps.cn/%s/html/%s.html' % (year, pmid)
            paper["doi"] = article.doi if article.doi else ''
            paper["doi_link"] = 'https://doi.org/' + paper["doi"]
            self.metadata.append(paper)

            pbar.set_description("Processing %s" % pmid)

        # Don't save when cannot find any results.
        if len(self.metadata) > 0:
            logger.info("Find %s new articles." % len(self.metadata))
            write_json(self.metadata, self.dest_file)
        else:
            logger.warning("Cannot find any new articles.")

# paper_metadata
# {
#     "pmid": "",
#     "pmcid": "",
#     "pmc_link": "",
#     "pubmed_link": "",
#     "abstract": "",
#     "title": "",
#     "authors": "",
#     "journal": "",
#     "publication": "",
#     "doi": "",
#     "offline_link": ""
# }


def pdf_to_html(dest_dir, pdf_file):
    if os.path.exists("/usr/local/bin/pdf2htmlEX"):
        output = subprocess.call(["pdf2htmlEX", "--zoom", "1.5",
                                  pdf_file, "--dest-dir", dest_dir], shell=False)
        if output == 0:
            return True
        else:
            return False
    else:
        pdf_dir = os.path.dirname(pdf_file)
        command = f"docker run --rm -v {pdf_dir}:{pdf_dir} -v {dest_dir}:{dest_dir} -it bwits/pdf2htmlex:latest pdf2htmlEX --zoom 1.5 {pdf_file} --dest-dir {dest_dir}"
        output = subprocess.call(command, shell=True)
        if output == 0:
            return True
        else:
            return False

def download_pmc(pmcid, filepath):
    url = 'https://www.ncbi.nlm.nih.gov/pmc/articles/' + \
        str(pmcid) + '/'
    html = requests.get(url, headers=headers)
    if html.status_code == 200:
        soup = BeautifulSoup(html.text, 'html.parser')
        pdf_links = soup.find_all('a', attrs={'class': 'int-view'})
        logger.info("Find pdf links: %s" % pdf_links)
        if pdf_links:
            pdf_links = [pdf_link.get('href') for pdf_link in pdf_links]
            pdf_link = set(pdf_links)[0]
            pdf_link = 'https://www.ncbi.nlm.nih.gov' + pdf_link
            pdf = requests.get(pdf_link, headers=headers)
            if pdf.status_code == 200:
                with open(filepath, 'wb') as f:
                    f.write(pdf.content)
                    logger.info("Download %s succssfully." % filepath)
            else:
                logger.warning(
                    "Download %s failed, status code is %s." % (url, pdf.status_code))
    else:
        logger.warning(
            "Download %s failed, status code is %s." % (url, html.status_code))


@click.group()
def pubmed():
    pass


@pubmed.command(help="Fetch metadata for articles.")
@click.option('--delay', '-d', required=False, type=int, default=1,
              help="How many seconds do you want to delay between each http request?")
@click.option('--output-file', '-o', required=True,
              help="The file which saved the metadata.")
@click.option('--config', '-c', required=True,
              type=click.Path(exists=True, file_okay=True, dir_okay=False),
              help="Where is the config file.")
def fetch_metadata(output_file, config, delay):
    with open(os.path.abspath(config), 'r') as f:
        c = json.load(f)
        query_str = c.get('query_str')
        formated_query_str = query_str.replace("'", "\"")
        output_file = os.path.abspath(output_file)
        if os.path.exists(output_file):
            logger.warning(
                "%s exists, please delete it firstly and retry." % output_file)
        else:
            output_dir = os.path.dirname(output_file)
            files = [os.path.join(output_dir, i)
                     for i in os.listdir(output_dir) if i.endswith(".json")]
            pubmed = PubMed(dest_file=output_file,
                            delay=delay)
            pubmed.batch_query_pmids(formated_query_str)
            pubmed.remove_dup_pmids(files)
            pubmed.fetch_save_metadata()

            if pubmed.counts > 0:
                dirname = os.path.dirname(config)
                history_file = os.path.join(dirname, 'history.json')
                history = read_json(history_file) or []
                history_item = {
                    "time": str(datetime.datetime.now()),
                    "query_str": query_str,
                    "total_articles": pubmed.counts,
                    "duplicated_articles": pubmed.counts - len(pubmed.pmids),
                    "valid_articles": len(pubmed.pmids),
                    "filename": output_file
                }
                history.append(history_item)
                logger.info("Fetch articles succssfully (%s)." %
                               history_item)
                write_json(history, history_file)


@pubmed.command(help="Fetch the full text for articles.")
@click.option('--metadata-file', '-m', required=True,
              help="The file which saved the metadata.")
@click.option('--output-dir', '-o', required=True,
              help="The directory which saved the full text.")
def fetch_pdf(metadata_file, output_dir):
    if not os.path.exists(metadata_file):
        logger.warning("Cannot find the metadata file.")
        raise Exception("Cannot find the metadata file.")

    metadata_file = os.path.abspath(metadata_file)
    output_dir = os.path.abspath(output_dir)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    metadata = read_json(metadata_file)
    if metadata is None:
        logger.warning("Cannot find the metadata file.")
        raise Exception("Cannot find the metadata file.")

    for i in metadata:
        pmcid = i.get('pmcid')
        pmid = i.get('pmid')
        scihub = i.get('doi')

        if os.path.exists(os.path.join(output_dir, str(pmid) + '.pdf')):
            logger.info("%s.pdf exists in %s, skip it." % (pmid, output_dir))
            continue

        if pmcid:
            logger.info("Download %s from PMC." % pmid)
            download_pmc(pmcid, os.path.join(output_dir, str(pmid) + '.pdf'))
            logger.info("\n\n")
        elif scihub:
            logger.info("Download %s from scihub." % pmid)
            sh = SciHub()
            sh.download(scihub, destination=output_dir, path=str(pmid) + '.pdf')
        else:
            logger.info("Cannot find the full text for %s" % pmid)
            
@pubmed.command(help="Convert pdf to html.")
@click.option('--pdf-dir', '-p', required=True,
                help="The directory which saved the pdf.")
@click.option('--html-dir', '-h', required=True,
                help="The directory which saved the html.")
def pdf2html(pdf_dir, html_dir):
    pdf_dir = os.path.abspath(pdf_dir)
    html_dir = os.path.abspath(html_dir)
    if not os.path.exists(html_dir):
        os.makedirs(html_dir)
    pdfs = [os.path.join(pdf_dir, i)
            for i in os.listdir(pdf_dir) if i.endswith(".pdf")]
    for pdf in pdfs:
        html_filename = os.path.basename(pdf).replace(".pdf", ".html")
        html_file = os.path.join(html_dir, html_filename)
        if os.path.exists(html_file):
            logger.info("Skip %s" % pdf)
            continue

        if pdf_to_html(html_dir, pdf):
            embed_styles(html_file)


main = click.CommandCollection(sources=[pubmed])

if __name__ == '__main__':
    main()
