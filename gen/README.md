CARA Python generator
=====================

Using the [generic generator framework for capnp](https://github.com/chainreactionmfg/capnp_generic_gen), this generates the python bindings for a given capnp schema to cara. Invoked like so:

    capnp compile -ocara <capnp_file.capnp>

Here is a sample capnproto schema and output:

    # sample_schema.capnp
    const c :Float32 = 3.0e8 $ann("const before annotation declaration");
    annotation ann(*) :Text;
    enum from {  # python keywords in struct, interface and enum names are escaped with a _ suffix.
      first @0 $ann("enumerant");
      from @1;  # python keywords in fields, methods and enumerants are fine.
    }
    
    struct Struct $ann("struct") {
      data @0 :Interface;
      interface Interface {
        ping @0 (input :Text $ann("input")) ->
            (output :Text $ann("output")) 
            $ann("method");
      }
    }
    

Output:

  import cara
  ann = cara.Annotation(name='ann')
  c = cara.Const(name='c')
  Enum = cara.Enum(name='Enum')
  Struct = cara.Struct(name='Struct')
  Struct.Interface = cara.Interface(name='Interface')

  ann.FinishDeclaration(type=cara.Text)
  c.FinishDeclaration(type=cara.Float32, value=3.0e8, annotations=[ann("const before annotation declaration")])
  Enum.FinishDeclaration(enumerants=[cara.Enumerant(name="first", ordinal=0, annotations=[ann("enumerant")]), cara.Enumerant(name="from", ordinal=1)])
  Struct.FinishDeclaration(fields=[cara.Field(name="data", type=Interface)], annotations = [ann("struct")])
  Interface.FinishDeclaration(methods=[cara.Method(name="ping", id=0, input_params=[cara.Param(name="input", type=cara.Text, annotations=[ann("input")])], output_params=[cara.Param(name="output", type=cara.Text)], annotations=[ann("method")])])

Obviously the output isn't the most pep8-friendly. I recommend piping it
through `autopep8 --experimental` to get the best looking code.
    
Implementation Discussion
--------------------------------

First we will output all declarations, sort of like forward declaring them in
C++, but Python doesn't have that. Second, each declaration will be finished.

Since capnp schemas allow using schema types that aren't declared or fully
declared yet, we need forward declaration of some sort. One way is to declare
types as much as possible and then move parts of the declaration that can't be
put there (due to use of later-defined types) later on, but that is much more
complicated in terms of code and creates code that is a hybrid of fully
defining types and forward declaring them.
