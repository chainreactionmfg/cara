import glob

def task_test():
    return {
        'actions': ['py.test --cov cara --cov cara_pseud'],
        'file_dep': glob.glob('*.py'),
        'verbosity': 2,
    }
