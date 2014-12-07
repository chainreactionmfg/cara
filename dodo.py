import glob

def task_test():
    return {
        'actions': ['py.test --cov cara --incremental'],
        'file_dep': glob.glob('*/*.py'),
        'verbosity': 2,
    }
