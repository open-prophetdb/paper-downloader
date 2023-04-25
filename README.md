# How to prepare papers for the NLP pipeline
## Fetch metadata

```
python main.py fetch-metadata -d 3 -o metadata/file.json -c config/pmids_config.json
```

## Fetch PDFs

```
python main.py fetch-pdf -m metadata/file.json -o ./pdf
```

## PDF to HTML

```
python main.py pdf2html -p ./pdf -h ./html
```

# How to setup the label studio
## Create a service account on the miniocloud

1. Login to the miniocloud
2. Click on the `Service Accounts` tab
3. Click on `Create Service Account`
4. Fill in the form and click on `Create` [Don't enable `Restrict with policy`]

## Enable https on the miniocloud

## Setup the label studio
1. Create a project on the label studio
2. Go to the `Settings` tab
3. Click on `Cloud Storage` tab
4. Click on `Add Source Storage` and fill in the form 

> NOTE: 
> 1. You must use the https url of the miniocloud
> 2. You must enable the `Use pre-signed URLs` option, so the label studio can generate the pre-signed url for the html files automatically.

## Prepare the data for the label studio
1. Each task in the label studio is a single HTML file
2. The HTML files must be stored in the miniocloud
3. You must create a `tasks.json` file that contains the list of the HTML files
4. Each task in the `tasks.json` file must have the following format:
```
# `html` is a variable that contains the path to the html file, you need to keep it same with your labeling interface settings.
# Label studio will automatically fetch the html file from the miniocloud
[
    {
        "html": "s3://<bucket_name>/<path_to_the_html_file>",
        "pdf": "<embed src='https://<bucket_name>.minio.<region>.miniocloud.com/<path_to_the_pdf_file>' width='100%' height='100%' type='application/pdf'>"
    }
]

# NOTE:
# If you want to show the pdf file on Chrome, it may complain about the sandboxing. I've no idea how to fix it. But it works on Firefox.
```

## How to prepare your data
1. To choose a query string that can be used to query pubmed for the papers you want to label
2. To Prepare a yaml file which contains two fields: `query_str`, `author` and `download_pdf`. You need to use plain text editor or code editor to create the yaml file. The yaml file must have the following format:

    ```yaml
    query_str: "your query string"
    author: "your name"
    download_pdf: true
    ```

    > NOTE:
    > 1. The `query_str` field is used to query pubmed for the papers you want to label
    > 2. The `author` field is used to identify who is labeling the papers
    > 3. The `download_pdf` field is used to indicate whether the pipeline should download the pdf files of the papers automatically. If you set it to `true`, the pipeline will download the pdf files of the papers automatically. If you set it to `false`, the pipeline will not download the pdf files of the papers automatically. You can download the pdf files manually by `paper-downloader` tool. After downloading all pdfs of the papers, you need to reimport the metadata file to the label studio. The metadata file will be stored in the `metadata/<project_name>` folder. The pdf files will be stored in the `pdf` folder. [NOTE: Not all the papers have pdf files, if you see a paper that doesn't have a pdf file on label studio, it means the pipeline couldn't download the pdf file of the paper automatically. You can download the pdf file manually and upload it to the pdf folder]
    > 4. The `download_pdf` field is optional. If you don't set it, the pipeline will not download the pdf files of the papers automatically.

3. To upload the yaml file to the `config/<project_name>` folder
4. Wait a few minutes for the pipeline to fetch the papers and generate the metadata file for the papers. The metadata file will be stored in the `metadata/<project_name>` folder. If you want to check the progress of the pipeline, you can check the dingtalk group. But if you enable the `download_pdf` field, the pipeline will take a long time to download the pdf files of the papers. So you can check the progress of the pipeline by checking the `pdf/<project_name>` folder. The pipeline will download the pdf files of the papers one by one. If you see a pdf file in the `pdf/<project_name>` folder, it means the pipeline has finished downloading the pdf file of the paper.
5. If you see a notification in the dingtalk group, it means the pipeline has finished fetching the metadata of papers. After that, the system administrator will also get the notification and upload the metadata file to the label studio and download all the pdf files of the papers. The pdf files will be stored in the `pdf/<project_name>` folder. [**NOTE: Not all the papers have pdf files, if you see a paper that doesn't have a pdf file on label studio, it means the pipeline couldn't download the pdf file of the paper automatically. You can download the pdf file manually and upload it to the pdf folder**]
6. To start labeling the papers;