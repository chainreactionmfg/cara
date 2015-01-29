import os

generator_filename = os.path.join('gen', 'capnpc-cara')
if not os.path.exists(generator_filename):
    with open(generator_filename, 'w') as generator:
        generator.write('')
