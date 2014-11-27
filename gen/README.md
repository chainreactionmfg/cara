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
  ann = cara.Annotation(name="ann", type=cara.Text)
    c = cara.Const(name="c", type=cara.Float32, value=3.0e8, annotations=[ann("const before annotation declaration")])
    @cara.define
    def from_():
      return cara.Enum(name="from", enumerants=[cara.Enumerant(name="first", ordinal=0, annotations=[ann("enumerant")]), cara.Enumerant(name="from", ordinal=1)])
  @cara.define
  def Struct():
    @cara.define
    def Interface():
      return cara.Interface(name="Interface", methods=[cara.Method(name="ping", id=0, input_params=[cara.Param(name="input", type=cara.Text, annotations=[ann("input")])], output_params=[cara.Param(name="output", type=cara.Text)], annotations=[ann("method")])])
    return cara.Struct(name="Struct", nested=[Interface], fields=[cara.Field(name="data", type=Interface)], annotations=[ann("struct")])

Obviously the output isn't the most pep8-friendly. I recommend piping it
through `autopep8 --experimental` to get the best looking code.
    

