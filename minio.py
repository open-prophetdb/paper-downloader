import os
import subprocess
from watchdog.observers import Observer
from watchdog.events import *
import time

# Define a function to handle events
def handle_pdf_event(filepath):
    # If you change the directory structure, you need to change the parent_dir
    print("Find a new file: ", filepath)
    if os.path.isfile(filepath) and filepath.endswith(".pdf"):
        dirname = os.path.dirname(filepath)
        dest_path = "/data/prophetdb/prophetdb-studio/data/publications/2023/html"
        cmd = f"/data/prophetdb/prophetdb-studio/paper-downloader/.venv/bin/python /data/prophetdb/prophetdb-studio/paper-downloader/main.py pdf2html -p {dirname} -h {dest_path}"
        output = subprocess.check_output(cmd, shell=True)
        print(output)
    else:
        print("The file is not a json file")


class FileEventHandler(FileSystemEventHandler):
    def __init__(self):
        FileSystemEventHandler.__init__(self)

    def on_moved(self, event):
        if event.is_directory:
            print("directory moved from {0} to {1}".format(event.src_path,event.dest_path))
        else:
            print("file moved from {0} to {1}".format(event.src_path,event.dest_path))

    def on_created(self, event):
        if event.is_directory:
            print("directory created:{0}".format(event.src_path))
        else:
            print("file created:{0}".format(event.src_path))
            if event.src_path.startswith("/data/prophetdb/prophetdb-studio/data/publications/2023/pdf"):
                if event.src_path.endswith(".pdf"):
                    handle_pdf_event(event.src_path)

    def on_deleted(self, event):
        if event.is_directory:
            print("directory deleted:{0}".format(event.src_path))
        else:
            print("file deleted:{0}".format(event.src_path))

    def on_modified(self, event):
        if event.is_directory:
            print("directory modified:{0}".format(event.src_path))
        else:
            print("file modified:{0}".format(event.src_path))


def main():
    observer = Observer()
    event_handler = FileEventHandler()
    observer.schedule(event_handler, "/data/prophetdb/prophetdb-studio/data/publications/2023", True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
