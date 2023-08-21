import os
import re
import click
import requests
import logging
import time
import json
import copy
import hashlib
import csv
import yaml
from datetime import datetime
import subprocess
from tqdm import tqdm
from metapub import PubMedFetcher
from lxml import etree
from bs4 import BeautifulSoup
import urllib3
import bibtexparser
from retrying import retry

# log config
# create logger
logger = logging.getLogger("paper-downloader")
logger.setLevel(logging.DEBUG)

def send_notification(msg, access_token=None):
    # Replace with your own DingTalk Bot webhook URL
    url = f"https://oapi.dingtalk.com/robot/send?access_token={access_token}"

    headers = {"Content-Type": "application/json;charset=utf-8"}

    data = {
        "msgtype": "text",
        "text": {"content": msg},
    }

    r = requests.post(url, headers=headers, data=json.dumps(data))
    logger.info(r.text)


def set_log(log_path):
    # create console handler and set level to debug
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.DEBUG)
    # create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    # add formatter to console handler
    fh.setFormatter(formatter)
    # add console handler to logger
    logger.addHandler(fh)


#
urllib3.disable_warnings()

# constants
SCHOLARS_BASE_URL = "https://scholar.google.com/scholar"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:27.0) Gecko/20100101 Firefox/27.0"
}

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
}


def read_file_as_text(text_file):
    with open(text_file, "r") as f:
        return f.read()


def read_css_file(file):
    """Read the CSS contents from a file."""
    css_path = os.path.join(os.path.dirname(__file__), "css", file)
    with open(css_path, "r") as css_file:
        return css_file.read()


def embed_styles(html_file):
    if os.path.exists(html_file):
        text = read_file_as_text(html_file)
        soup = BeautifulSoup(text, "html.parser")
        css = read_css_file("pdf.css")

        # Create a new `style` element and insert the CSS contents
        style_tag = soup.new_tag("style")
        style_tag.string = css
        if soup.head is None:
            head = soup.new_tag("head")
            head.append(style_tag)
            soup.insert(0, head)
        else:
            soup.head.append(style_tag)

        with open(html_file, "w") as f:
            f.write(str(soup))
    else:
        logger.warning("No such html file (%s), please check it." % html_file)


def write_csv(data, filename):
    headers = data[0].keys()
    with open(filename, "w", newline="") as myfile:
        writer = csv.DictWriter(myfile, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)


def write_json(data, filename):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)


def read_json(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
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
        self.sess.headers = HEADERS  # type: ignore
        self.available_base_url_list = self._get_available_scihub_urls()
        self.base_url = self.available_base_url_list[0] + "/"

    def _get_available_scihub_urls(self):
        """
        Finds available scihub urls via https://sci-hub.now.sh/
        """
        return ["https://sci-hub.ee", "https://sci-hub.ru", "https://sci-hub.se"]
        urls = []
        res = requests.get("https://sci-hub.now.sh/")
        s = self._get_soup(res.content)
        for a in s.find_all("a", href=True):
            if "sci-hub." in a["href"]:
                urls.append(a["href"])
        return urls

    def set_proxy(self, proxy):
        """
        set proxy for session
        :param proxy_dict:
        :return:
        """
        if proxy:
            self.sess.proxies = {
                "http": proxy,
                "https": proxy,
            }

    def _change_base_url(self):
        if not self.available_base_url_list:
            raise Exception("Ran out of valid sci-hub urls")
        del self.available_base_url_list[0]
        self.base_url = f"{self.available_base_url_list[0]}/"
        logger.info("I'm changing to {}".format(self.available_base_url_list[0]))

    def search(self, query, limit=10, download=False):
        """
        Performs a query on scholar.google.com, and returns a dictionary
        of results in the form {'papers': ...}. Unfortunately, as of now,
        captchas can potentially prevent searches after a certain limit.
        """
        start = 0
        results = {"papers": []}

        while True:
            try:
                res = self.sess.get(
                    SCHOLARS_BASE_URL, params={"q": query, "start": start}
                )
            except requests.exceptions.RequestException as e:
                results["err"] = (
                    "Failed to complete search with query %s (connection error)" % query
                )
                return results

            s = self._get_soup(res.content)
            papers = s.find_all("div", class_="gs_r")

            if not papers:
                if "CAPTCHA" in str(res.content):
                    results["err"] = (
                        "Failed to complete search with query %s (captcha)" % query
                    )
                return results

            for paper in papers:
                if not paper.find("table"):
                    source = None
                    pdf = paper.find("div", class_="gs_ggs gs_fl")
                    link = paper.find("h3", class_="gs_rt")

                    if pdf:
                        source = pdf.find("a")["href"]
                    elif link.find("a"):
                        source = link.find("a")["href"]
                    else:
                        continue

                    results["papers"].append({"name": link.text, "url": source})

                    if len(results["papers"]) >= limit:
                        return results

            start += 10

    @retry(wait_random_min=100, wait_random_max=1000, stop_max_attempt_number=10)
    def download(self, identifier, destination="", path=None):
        """
        Downloads a paper from sci-hub given an indentifier (DOI, PMID, URL).
        Currently, this can potentially be blocked by a captcha if a certain
        limit has been reached.
        """
        data = self.fetch(identifier)

        if not "err" in data:
            self._save(
                data["pdf"], os.path.join(destination, path if path else data["name"])
            )
            return True
        else:
            return False

    def fetch(self, identifier):
        """
        Fetches the paper by first retrieving the direct link to the pdf.
        If the indentifier is a DOI, PMID, or URL pay-wall, then use Sci-Hub
        to access and download paper. Otherwise, just download paper directly.
        """

        try:
            url = self._get_direct_url(identifier)
            logger.info("Resolved url %s for identifier %s" % (url, identifier))

            # verify=False is dangerous but sci-hub.io
            # requires intermediate certificates to verify
            # and requests doesn't know how to download them.
            # as a hacky fix, you can add them to your store
            # and verifying would work. will fix this later.
            res = self.sess.get(url, verify=False)

            if res.headers["Content-Type"] != "application/pdf":
                self._change_base_url()
                logger.info(
                    "Failed to fetch pdf with identifier %s "
                    "(resolved url %s) due to captcha" % (identifier, url)
                )
                raise CaptchaNeedException(
                    "Failed to fetch pdf with identifier %s "
                    "(resolved url %s) due to captcha" % (identifier, url)
                )
                # return {
                #     'err': 'Failed to fetch pdf with identifier %s (resolved url %s) due to captcha'
                #            % (identifier, url)
                # }
            else:
                return {
                    "pdf": res.content,
                    "url": url,
                    "name": self._generate_name(res),
                }

        except requests.exceptions.ConnectionError:
            logger.info(
                "Cannot access {}, changing url".format(self.available_base_url_list[0])
            )
            self._change_base_url()

        except requests.exceptions.RequestException as e:
            logger.info(
                "Failed to fetch pdf with identifier %s (resolved url %s) due to request exception."
                % (identifier, url)
            )
            return {
                "err": "Failed to fetch pdf with identifier %s (resolved url %s) due to request exception."
                % (identifier, url)
            }

    def _get_direct_url(self, identifier):
        """
        Finds the direct source url for a given identifier.
        """
        id_type = self._classify(identifier)

        return (
            identifier
            if id_type == "url-direct"
            else self._search_direct_url(identifier)
        )

    def _search_direct_url(self, identifier):
        """
        Sci-Hub embeds papers in an iframe. This function finds the actual
        source url which looks something like https://moscow.sci-hub.io/.../....pdf.
        """
        res = self.sess.get(self.base_url + identifier, verify=False)
        logger.info("Getting direct url %s" % self.base_url + identifier)
        s = self._get_soup(res.content)
        iframe = s.find("iframe")
        if iframe:
            return (
                iframe.get("src")
                if not iframe.get("src").startswith("//")
                else "http:" + iframe.get("src")
            )

    def _classify(self, identifier):
        """
        Classify the type of identifier:
        url-direct - openly accessible paper
        url-non-direct - pay-walled paper
        pmid - PubMed ID
        doi - digital object identifier
        """
        if identifier.startswith("http") or identifier.startswith("https"):
            if identifier.endswith("pdf"):
                return "url-direct"
            else:
                return "url-non-direct"
        elif identifier.isdigit():
            return "pmid"
        else:
            return "doi"

    def _save(self, data, path):
        """
        Save a file give data and a path.
        """
        with open(path, "wb") as f:
            f.write(data)

    def _get_soup(self, html):
        """
        Return html soup.
        """
        return BeautifulSoup(html, "html.parser")

    def _generate_name(self, res):
        """
        Generate unique filename for paper. Returns a name by calcuating
        md5 hash of file contents, then appending the last 20 characters
        of the url which typically provides a good paper identifier.
        """
        name = res.url.split("/")[-1]
        name = re.sub("#view=(.+)", "", name)
        pdf_hash = hashlib.md5(res.content).hexdigest()
        return "%s-%s" % (pdf_hash, name[-20:])


def get_impact_factor(journal):
    from impact_factor.core import Factor

    fa = Factor()

    results = fa.search(journal)
    if len(results) == 1:
        return (results[0].get("factor"), results[0].get("journal"))
    else:
        return (-1, "Unknown")


class PubMed(PubMedFetcher):
    """Get articles from pubmed.

    Steps:
        pubmed = PubMed()
        pubmed.batch_query_pmids(query_str)
        pubmed.remove_dup_pmids(files)
        pubmed.fetch_save_metadata()
    """

    def __init__(
        self,
        method="eutils",
        cachedir=".cache",
        delay=1,
        dest_file=".",
        get_impact_factor_fn=None,
    ):
        self.counts = 0
        self.delay = delay
        self.pmids = []
        self.author = "Anonymous"
        self.metadata = []
        self.dest_file = dest_file
        self.duplicated_papers = []
        self.get_impact_factor_fn = get_impact_factor_fn

        if os.path.exists(dest_file):
            raise Exception("%s does exist, please delete it and retry." % dest_file)

        super().__init__(method, cachedir)

    def _count(self, query_str):
        result = self.qs.esearch(
            {
                "db": "pubmed",
                "term": query_str,
                "rettype": "count",
                "retmax": 250,
                "retstart": 0,
            }
        )
        return int(etree.fromstring(result).find("Count").text.strip())

    def batch_query_pmids(self, query_str, author="Anonymous", token=None):
        logger.info("Fetch the metadata with query_str (%s)..." % query_str)
        pmids = []
        self.counts = self._count(query_str)
        for i in range(0, (self.counts // 250) + 1):
            time.sleep(self.delay)
            r = self.pmids_for_query(query_str, retmax=250, retstart=i * 250)
            logger.info("Fetch the first %s articles" % len(r))
            if token:
                send_notification(
                    f"Fetch the {(i + 1) * 250}/{self.counts} articles", token
                )
            pmids.extend(r)
        self.pmids = pmids
        self.author = author
        logger.info("Get %s papers" % len(pmids))

    def remove_dup_pmids(self, files):
        logger.info("Remove the duplicated articles by %s..." % files)
        for file in files:
            try:
                articles = read_json(file)
                if type(articles) == list and len(articles) > 0:
                    pmids = [
                        str(article.get("pmid"))
                        for article in articles
                        if article.get("pmid")
                    ]
                    total = len(self.pmids)

                    duplicated_papers = [
                        article
                        for article in articles
                        if str(article.get("pmid")) in self.pmids
                    ]
                    self.duplicated_papers.extend(duplicated_papers)
                    logger.info("Find %s duplicated papers" % len(duplicated_papers))

                    self.pmids = [pmid for pmid in self.pmids if pmid not in pmids]
                    logger.info(
                        "Find %s duplicated pmids and %s unique pmids"
                        % ((total - len(self.pmids)), len(self.pmids))
                    )

            except Exception as e:
                logger.error("Load %s error, reason: %s" % (file, e))

    def fetch_save_metadata(self):
        logger.info("Fetch the metadata for articles...")
        pbar = tqdm(self.pmids)

        for pmid in pbar:
            try:
                paper = {}
                article = self.article_by_pmid(pmid)
                paper["tag"] = self.author
                paper["pmid"] = int(pmid)
                paper["pmcid"] = article.pmc if article.pmc else ""
                paper["pmc_link"] = (
                    "https://www.ncbi.nlm.nih.gov/pmc/articles/" + article.pmc
                    if article.pmc
                    else ""
                )
                paper["pubmed_link"] = "https://pubmed.ncbi.nlm.nih.gov/" + pmid
                paper["abstract"] = (
                    article.abstract.replace("\n", " ")
                    if article.abstract is not None
                    else ""
                )
                paper["title"] = article.title
                paper["imported_date"] = datetime.now().strftime("%Y-%m-%d")
                paper["authors"] = ", ".join(article.authors)
                paper["journal_abbr"] = article.journal
                paper["journal"] = "Unknown"
                paper["pdf"] = ""
                paper["html"] = ""
                paper["impact_factor"] = -1
                paper["publication"] = article.year
                paper["doi"] = article.doi if article.doi else ""
                paper["doi_link"] = "https://doi.org/" + paper["doi"]

                if self.get_impact_factor_fn:
                    (
                        paper["impact_factor"],
                        paper["journal"],
                    ) = self.get_impact_factor_fn(article.journal)

                self.metadata.append(paper)
            except Exception as e:
                logger.error("Fetch metadata for %s error, reason: %s" % (pmid, e))

            pbar.set_description("Processing %s" % pmid)

        # Don't save when cannot find any results.
        if len(self.metadata) > 0:
            logger.info("Find %s new articles." % len(self.metadata))
            write_json(self.metadata, self.dest_file)
        else:
            write_json([], self.dest_file)
            logger.warning("Cannot find any new articles.")

        if self.duplicated_papers:
            logger.info("Find %s duplicated articles." % len(self.duplicated_papers))
            fileprefix, _ = os.path.splitext(self.dest_file)
            filepath = fileprefix + "_duplicated.json"
            write_json(self.duplicated_papers, filepath)


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
#     "pdf": ""
#     "html": ""
# }


def pdf_to_html(dest_dir, pdf_file):
    if os.path.exists("/usr/local/bin/pdf2htmlEX"):
        output = subprocess.call(
            ["pdf2htmlEX", "--zoom", "1.5", pdf_file, "--dest-dir", dest_dir],
            shell=False,
        )
        if output == 0:
            return True
        else:
            return False
    else:
        pdf_dir = os.path.dirname(pdf_file)
        command = f"docker run --rm -v {pdf_dir}:{pdf_dir} -v {dest_dir}:{dest_dir} -it bwits/pdf2htmlex:latest pdf2htmlEX --zoom 1.5 {pdf_file} --dest-dir {dest_dir}"
        output = subprocess.call(command, shell=True)
        if output == 0:
            html_filename = os.path.basename(pdf_file).replace(".pdf", ".html")
            html_file = os.path.join(dest_dir, html_filename)
            embed_styles(html_file)
            return True
        else:
            return False


def download_pmc(pmcid, filepath):
    url = "https://www.ncbi.nlm.nih.gov/pmc/articles/" + str(pmcid) + "/"
    html = requests.get(url, headers=headers)
    if html.status_code == 200:
        soup = BeautifulSoup(html.text, "html.parser")
        pdf_links = soup.find_all("a", attrs={"class": "int-view"})
        logger.info("Find pdf links: %s" % pdf_links)
        if pdf_links:
            pdf_links = [pdf_link.get("href") for pdf_link in pdf_links]
            pdf_link = list(set(pdf_links))[0]
            pdf_link = "https://www.ncbi.nlm.nih.gov" + pdf_link
            pdf = requests.get(pdf_link, headers=headers)
            if pdf.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(pdf.content)
                    logger.info("Download %s succssfully." % filepath)
                return True
            else:
                logger.warning(
                    "Download %s failed, status code is %s." % (url, pdf.status_code)
                )
                return False
    else:
        logger.warning(
            "Download %s failed, status code is %s." % (url, html.status_code)
        )
        return False


@click.group()
def pubmed():
    pass


@pubmed.command(help="Fetch metadata for articles.")
@click.option(
    "--delay",
    "-d",
    required=False,
    type=int,
    default=1,
    help="How many seconds do you want to delay between each http request?",
)
@click.option(
    "--output-file", "-o", required=True, help="The file which saved the metadata."
)
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Where is the config file.",
)
@click.option(
    "--logpath",
    "-l",
    required=False,
    default="/var/log/paper-downloader.log",
    help="Where is the log file.",
)
@click.option(
    "--token", "-t", required=False, default=None, help="The token for dingtalk."
)
def fetch_metadata(output_file, config, delay, logpath, token):
    set_log(logpath)

    if os.path.exists(output_file):
        raise Exception(
            """
%s exists. if you want to update the metadata, please delete it first or rename it.
"""
            % output_file
        )

    if not os.path.exists(os.path.dirname(output_file)):
        os.makedirs(os.path.dirname(output_file))

    with open(os.path.abspath(config), "r") as f:
        if config.endswith(".json"):
            c = json.load(f)
        elif config.endswith(".yaml"):
            c = yaml.load(f, Loader=yaml.FullLoader)
        else:
            raise Exception("Please check your config file.")

        query_str = str(c.get("query_str"))
        author = c.get("author")

        if not query_str:
            logger.warning("Please check your config file.")
            raise Exception(
                "Please check your config file, It don't contain query_str."
            )

        formated_query_str = query_str.replace("'", '"')
        output_file = os.path.abspath(output_file)

        output_dir = os.path.dirname(output_file)
        files = [
            os.path.join(output_dir, i)
            for i in os.listdir(output_dir)
            if i.endswith(".json")
        ]
        pubmed = PubMed(
            dest_file=output_file, delay=delay, get_impact_factor_fn=get_impact_factor
        )
        pubmed.batch_query_pmids(
            formated_query_str, author if author else "Anonymous", token=token
        )
        send_notification(f"Fetch articles succssfully ({pubmed.counts}).", token)
        pubmed.remove_dup_pmids(files)
        pubmed.fetch_save_metadata()

        if pubmed.counts > 0:
            dirname = os.path.dirname(config)
            history_file = os.path.join(dirname, "history.json")
            history = read_json(history_file) or []
            history_item = {
                "time": str(datetime.now()),
                "query_str": query_str,
                "total_articles": pubmed.counts,
                "duplicated_articles": pubmed.counts - len(pubmed.pmids),
                "valid_articles": len(pubmed.pmids),
                "filename": output_file,
            }
            send_notification(
                f"Duplicated articles: {pubmed.counts - len(pubmed.pmids)}, valid articles: {len(pubmed.pmids)}",
                token,
            )
            history.append(history_item)
            logger.info("Fetch articles succssfully (%s)." % history_item)
            write_json(history, history_file)


def update_metadata(pmid, metadata, metadata_file, pdf_filepath, html_filepath):
    article_metadata = filter(lambda x: x.get("pmid") == pmid, metadata)

    for j in article_metadata:
        if os.path.isfile(pdf_filepath):
            pdf_url = "https://publications.3steps.cn/publications/pdf/%s.pdf" % pmid
            j[
                "pdf"
            ] = f"<embed src='{pdf_url}' width='100%' height='600px' type='application/pdf'>"

        # if os.path.isfile(html_filepath):
        #     j["html"] = 's3://publications/html/%s.html' % pmid
        j["html"] = "s3://publications/html/%s.html" % pmid

    with open(metadata_file, "w") as f:
        json.dump(metadata, f)


@pubmed.command(help="Fetch the full text for articles.")
@click.option(
    "--metadata-file", "-m", required=True, help="The file which saved the metadata."
)
@click.option(
    "--output-dir", "-o", required=True, help="The directory which saved the full text."
)
@click.option(
    "--logpath",
    "-l",
    required=False,
    default="/var/log/paper-downloader.log",
    help="Where is the log file.",
)
def fetch_pdf(metadata_file, output_dir, logpath):
    set_log(logpath)

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

    copied_metadata = copy.deepcopy(metadata)
    for i in metadata:
        pmcid = i.get("pmcid")
        pmid = i.get("pmid")
        scihub = i.get("doi")

        pdf_filepath = os.path.join(output_dir, str(pmid) + ".pdf")
        html_filepath = pdf_filepath.replace("pdf", "html")
        if os.path.exists(pdf_filepath):
            logger.info("%s.pdf exists in %s, skip it." % (pmid, output_dir))

            if not os.path.exists(html_filepath):
                try:
                    pdf_to_html(
                        os.path.dirname(html_filepath),
                        os.path.join(output_dir, pdf_filepath),
                    )
                except Exception as e:
                    logger.warning(
                        "Cannot convert %s.pdf to html. Please check the following messages: %s"
                        % (pmid, e)
                    )

            update_metadata(
                pmid, copied_metadata, metadata_file, pdf_filepath, html_filepath
            )
            continue

        if pmcid:
            logger.info("Download %s from PMC." % pmid)
            download_pmc(pmcid, pdf_filepath)
            logger.info("\n\n")
        elif scihub:
            logger.info("Download %s from scihub." % pmid)
            sh = SciHub()
            sh.download(scihub, destination=output_dir, path=str(pmid) + ".pdf")
        else:
            logger.info("Cannot find the full text for %s" % pmid)

        try:
            pdf_to_html(
                os.path.dirname(html_filepath), os.path.join(output_dir, pdf_filepath)
            )
        except Exception as e:
            logger.warning("Cannot convert %s.pdf to html." % pmid)

        update_metadata(
            pmid, copied_metadata, metadata_file, pdf_filepath, html_filepath
        )


@pubmed.command(help="Convert pdf to html.")
@click.option(
    "--pdf-dir", "-p", required=True, help="The directory which saved the pdf."
)
@click.option(
    "--html-dir", "-h", required=True, help="The directory which saved the html."
)
@click.option(
    "--logpath",
    "-l",
    required=False,
    default="/var/log/paper-downloader.log",
    help="Where is the log file.",
)
def pdf2html(pdf_dir, html_dir, logpath):
    set_log(logpath)

    pdf_dir = os.path.abspath(pdf_dir)
    html_dir = os.path.abspath(html_dir)
    if not os.path.exists(html_dir):
        os.makedirs(html_dir)
    pdfs = [os.path.join(pdf_dir, i) for i in os.listdir(pdf_dir) if i.endswith(".pdf")]
    for pdf in pdfs:
        logger.info("Convert pdf (%s) to html." % pdf)
        html_filename = os.path.basename(pdf).replace(".pdf", ".html")
        html_file = os.path.join(html_dir, html_filename)
        if os.path.exists(html_file):
            logger.info("Skip %s" % pdf)
            continue

        try:
            pdf_to_html(html_dir, pdf)
        except Exception as e:
            logger.error(e)
            logger.error("Convert %s failed." % pdf)
            continue


@pubmed.command(help="Convert bib file to a paper-downloader input file.")
@click.option("--bib-file", "-b", required=True, help="A path of bib file.")
@click.option("--output-file", "-o", required=True, help="An output file.")
@click.option(
    "--logpath",
    "-l",
    required=False,
    default="/var/log/paper-downloader.log",
    help="Where is the log file.",
)
def bib2pd(bib_file, output_file, logpath):
    set_log(logpath)

    if not os.path.exists(bib_file):
        raise Exception("Cannot find the bib file.")
    bib_file = os.path.abspath(bib_file)

    try:
        with open(bib_file, "r") as bibtex_file:
            bib_database = bibtexparser.load(bibtex_file)
            articles = bib_database.entries
            pmids = []
            for article in articles:
                pmid = article.get("pmid")
                if pmid:
                    pmids.append(pmid)

                url = article.get("url")
                if url:
                    if "pubmed" in url:
                        pmid = url.split("/")[-1]
                        pmids.append(pmid)

            query_str = " OR ".join(pmids)
            download_pdf = True
            output = {"query_str": query_str, "download_pdf": download_pdf}

            write_json(output, output_file)
    except Exception as e:
        raise Exception("Cannot load the bib file.")


cli = click.CommandCollection(sources=[pubmed])

if __name__ == "__main__":
    cli()
