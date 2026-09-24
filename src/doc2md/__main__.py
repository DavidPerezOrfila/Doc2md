import multiprocessing

from doc2md.cli import main


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
