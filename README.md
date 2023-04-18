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
python main.py pdf2html -p ./pdf -o ./html
```