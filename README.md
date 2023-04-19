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
{
    "data": {
        "html": "s3://<bucket_name>/<path_to_the_html_file>"
    }
}
```

## How to prepare your data
1. To choose a query string that can be used to query pubmed for the papers you want to label
2. To Prepare a yaml file which contains two fields: `query_str` and `author`
    ```yaml
    query_str: "your query string"
    author: "your name"
    ```
3. To upload the yaml file to the `config/<project_name>` folder
4. Wait a few minutes for the pipeline to fetch the papers and generate the metadata file for the papers. The metadata file will be stored in the `metadata/<project_name>` folder
5. If you see a notification in the dingtalk group, it means the pipeline has finished fetching the metadata of papers. After that, the system administrator will also get the notification and upload the metadata file to the label studio and download all the pdf files of the papers. The pdf files will be stored in the `pdf/<project_name>` folder. [NOTE: Not all the papers have pdf files, if you see a paper that doesn't have a pdf file on label studio, it means the pipeline couldn't download the pdf file of the paper automatically. You can download the pdf file manually and upload it to the pdf folder]
6. To start labeling the papers;