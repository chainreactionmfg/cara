#include <algorithm>
#include <map>
#include <memory>
#include <unordered_set>
#include <set>
#include <vector>
#include "generic.h"

#define MODULE_NAME "cara"
#define MODULE MODULE_NAME "."

/*
 * Terminology:
 * decl = declaration = "@cara.define\ndef X(): return BASE(...)", this
 *    creates a new scope in python
 * definition = "y = [Const, Annotation, Field, ...](args)", other than field,
 *    these define reusable variables in the current scope or, in the global
 *    scope, all children scopes.
 * orphans = definitions that couldn't be output in their parent declaration
 *    due to requiring another definition that hadn't been created yet.
 *
 */

template <typename T> using hash_set = std::unordered_set<T>;

struct Indent {
  uint amount;
  const static int INDENT = 2;
  Indent() = default;
  inline Indent(int amount): amount(amount * INDENT) {}

  inline Indent& operator++() { amount += INDENT; return *this; }
  inline Indent& operator--() { amount -= INDENT; return *this; }

  inline Indent operator+(Indent& other) { return Indent(amount + other.amount); }
  inline Indent operator+(int other) { return Indent(amount + other * INDENT); }
  inline Indent operator-(Indent& other) { return Indent(amount - other.amount); }
  inline Indent operator-(int other) { return Indent(amount - other * INDENT); }
  inline bool operator==(const Indent& other) const { return amount == other.amount; }
  inline bool operator!=(const Indent& other) const { return amount != other.amount; }

  struct Iterator {
    uint i;
    Iterator() = default;
    inline Iterator(uint i): i(i) {}
    inline char operator*() const { return ' '; }
    inline Iterator& operator++() { ++i; return *this; }
    inline Iterator operator++(int) { Iterator result = *this; ++i; return result; }
    inline bool operator==(const Iterator& other) const { return i == other.i; }
    inline bool operator!=(const Iterator& other) const { return i != other.i; }
  };

  inline size_t size() const { return amount; }

  inline Iterator begin() const { return Iterator(0); }
  inline Iterator end() const { return Iterator(amount); }
};

kj::String KJ_STRINGIFY(const Indent& indent) {
  kj::Vector<char> chars(indent.size());
  for (auto ch : indent) {
    chars.add(ch);
  }
  return kj::heapString(chars.begin(), chars.size());
}

std::string stringify(const hash_set<std::string>& set) {
  std::string out("[");
  int count = 0;
  for (auto it = set.begin(); it != set.end(); ++it, ++count) {
    out.append(*it);
    if (it != set.begin()) {
      out.append(", ");
    }
  }
  out.append("]");
  return std::move(out);
}

kj::String pop_back(std::vector<kj::String>& vect) {
  kj::String result = kj::str(vect.back());
  vect.pop_back();
  return result;
}

/*[[[cog
keyword_list = ', '.join('"%s"' % kw for kw in python_keywords)
cog.outl('const hash_set<std::string> KEYWORDS = {%s};' % keyword_list)
]]]*/
const hash_set<std::string> KEYWORDS = {"and", "as", "assert", "break", "class", "continue", "def", "del", "elif", "else", "except", "exec", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "not", "or", "pass", "print", "raise", "return", "try", "while", "with", "yield"};
//[[[end]]]
template<typename T>
kj::String check_keyword(T&& input) {
  if (KEYWORDS.count(kj::str(input).cStr()))
    return kj::str(kj::mv(input), "_");
  return kj::str(input);
}

class CapnpcCaraForwardDecls : public BaseGenerator {
 public:
  CapnpcCaraForwardDecls(SchemaLoader &schemaLoader, FILE* fd)
    : BaseGenerator(schemaLoader), fd_(fd) {
  }
 private:
  FILE* fd_;
  std::vector<std::string> decl_stack_;

  template<typename T>
  void outputDecl(std::string&& type, T&& name) {
    fprintf(
        fd_, "%s = " MODULE "%s(name=\"%s\")\n",
        kj::strArray(decl_stack_, ".").cStr(), type.c_str(), name.cStr());
  }

  bool pre_visit_decl(Schema, schema::Node::NestedNode::Reader decl) {
    decl_stack_.emplace_back(check_keyword(decl.getName()).cStr());
    return false;
  }

  bool post_visit_decl(Schema, schema::Node::NestedNode::Reader) {
    decl_stack_.pop_back();
    return false;
  }

  /*[[[cog
  decls = ['const', 'annotation', 'struct', 'enum', 'interface']
  for decl in decls:
    cog.outl('bool pre_visit_%s_decl(Schema, schema::Node::NestedNode::Reader decl) {' % decl)
    cog.outl('  outputDecl("%s", decl.getName());' % decl.title())
    cog.outl('  return false;')
    cog.outl('}')
  ]]]*/
  bool pre_visit_const_decl(Schema, schema::Node::NestedNode::Reader decl) {
    outputDecl("Const", decl.getName());
    return false;
  }
  bool pre_visit_annotation_decl(Schema, schema::Node::NestedNode::Reader decl) {
    outputDecl("Annotation", decl.getName());
    return false;
  }
  bool pre_visit_struct_decl(Schema, schema::Node::NestedNode::Reader decl) {
    outputDecl("Struct", decl.getName());
    return false;
  }
  bool pre_visit_enum_decl(Schema, schema::Node::NestedNode::Reader decl) {
    outputDecl("Enum", decl.getName());
    return false;
  }
  bool pre_visit_interface_decl(Schema, schema::Node::NestedNode::Reader decl) {
    outputDecl("Interface", decl.getName());
    return false;
  }
  //[[[end]]]
};

class CapnpcCara : public BaseGenerator {
 public:
  CapnpcCara(SchemaLoader &schemaLoader)
      : BaseGenerator(schemaLoader) {
    // start_decl("", "");
  }

 private:
  constexpr static const char FILE_SUFFIX[] = ".py";
  FILE* fd_;
  std::vector<std::string> decl_stack_;

  bool pre_visit_file(Schema schema, schema::CodeGeneratorRequest::RequestedFile::Reader requestedFile) override {
    kj::String outputFilename;
    auto inputFilename = requestedFile.getFilename();
    KJ_IF_MAYBE(loc, inputFilename.findLast('.')) {
      outputFilename = kj::str(inputFilename.slice(0, *loc), FILE_SUFFIX);
    } else {
      outputFilename = kj::str(inputFilename, FILE_SUFFIX);
    }
    fd_ = fopen(outputFilename.cStr(), "w");

    // Start the file
    outputLine("import " MODULE_NAME);
    outputLine("");
    outputLine("# Forward declarations:");

    // Output 'forward decls' first.
    CapnpcCaraForwardDecls decls(schemaLoader, fd_);
    decls.traverse_file(schema, requestedFile);
    outputLine("");
    outputLine("# Finishing declarations:");
    return false;
  }

  bool post_visit_file(Schema, schema::CodeGeneratorRequest::RequestedFile::Reader) override {
    fclose(fd_);
    return false;
  }

  void outputLine(kj::StringPtr line) {
    fwrite(line.cStr(), line.size(), 1, fd_);
    fputc('\n', fd_);
  }

  bool pre_visit_decl(Schema, schema::Node::NestedNode::Reader decl) {
    decl_stack_.emplace_back(check_keyword(decl.getName()).cStr());
    return false;
  }

  bool post_visit_decl(Schema, schema::Node::NestedNode::Reader) {
    decl_stack_.pop_back();
    return false;
  }

  bool post_visit_const_decl(Schema, schema::Node::NestedNode::Reader decl) {
    finish_decl(kj::str("name=\"", decl.getName(), "\", type=", pop_back(last_type_),
          ", value=", pop_back(last_value_), get_stored_annotations()));
    return false;
  }

  bool post_visit_annotation_decl(Schema schema, schema::Node::NestedNode::Reader decl) {
    auto proto = schema.getProto().getAnnotation();
    int count = 0;
    kj::Vector<kj::String> targets;
    /*[[[cog
    targets = [
        'struct', 'interface', 'group', 'enum', 'file', 'field', 'union',
        'group', 'enumerant', 'annotation', 'const', 'param', 'method',
    ]
    cog.outl('static const int NUM_TARGETS = %d;' % len(targets));
    for target in targets:
      # First count how many it targets.
      cog.outl('if (proto.getTargets%s()) {' % target.title())
      cog.outl('  ++count;')
      cog.outl('  targets.add(kj::str("\\"%s\\""));' % target)
      cog.outl('}')
      # Then if it matches everything, use Annotation.all
      # Otherwise, add each one to the line and count--
      # Only output an extra , if count > 0.
    ]]]*/
    static const int NUM_TARGETS = 13;
    if (proto.getTargetsStruct()) {
      ++count;
      targets.add(kj::str("\"struct\""));
    }
    if (proto.getTargetsInterface()) {
      ++count;
      targets.add(kj::str("\"interface\""));
    }
    if (proto.getTargetsGroup()) {
      ++count;
      targets.add(kj::str("\"group\""));
    }
    if (proto.getTargetsEnum()) {
      ++count;
      targets.add(kj::str("\"enum\""));
    }
    if (proto.getTargetsFile()) {
      ++count;
      targets.add(kj::str("\"file\""));
    }
    if (proto.getTargetsField()) {
      ++count;
      targets.add(kj::str("\"field\""));
    }
    if (proto.getTargetsUnion()) {
      ++count;
      targets.add(kj::str("\"union\""));
    }
    if (proto.getTargetsGroup()) {
      ++count;
      targets.add(kj::str("\"group\""));
    }
    if (proto.getTargetsEnumerant()) {
      ++count;
      targets.add(kj::str("\"enumerant\""));
    }
    if (proto.getTargetsAnnotation()) {
      ++count;
      targets.add(kj::str("\"annotation\""));
    }
    if (proto.getTargetsConst()) {
      ++count;
      targets.add(kj::str("\"const\""));
    }
    if (proto.getTargetsParam()) {
      ++count;
      targets.add(kj::str("\"param\""));
    }
    if (proto.getTargetsMethod()) {
      ++count;
      targets.add(kj::str("\"method\""));
    }
    //[[[end]]]
    auto line = kj::strTree(
          "name=\"", decl.getName(), "\", applies_to=");
    if (count == NUM_TARGETS) {
      line = kj::strTree(kj::mv(line), MODULE "Annotation.ALL");
    } else {
      line = kj::strTree(kj::mv(line), "[", kj::strArray(targets, ", "), "]");
    }
    line = kj::strTree(kj::mv(line), get_stored_annotations(), ", type=", pop_back(last_type_));
    finish_decl(line.flatten());
    return false;
  }

  bool post_visit_enum_decl(Schema, schema::Node::NestedNode::Reader decl) {
    finish_decl(kj::str("name=\"", decl.getName(), "\", enumerants=[",
          kj::strArray(enumerants_, ", "), "]", get_stored_annotations()));
    return false;
  }

  bool post_visit_struct_decl(Schema, schema::Node::NestedNode::Reader decl) {
    finish_decl(kj::str("name=\"", decl.getName(), "\", fields=[",
          kj::strArray(name_fields("Field"), ", "), "]", get_stored_annotations()));
    return false;
  }

  bool post_visit_interface_decl(Schema, schema::Node::NestedNode::Reader decl) {
    finish_decl(kj::str("name=\"", decl.getName(), "\", methods=[",
          kj::strArray(methods_, ", "), "]", get_stored_annotations()));
    return false;
  }

  // TODO: Add Struct and Interface

  std::vector<kj::String> last_type_;
  std::vector<kj::String> last_value_;
  std::vector<kj::String> fields_;
  kj::Vector<kj::String> annotations_;
  kj::String stored_annotations_ = kj::str("");

  std::vector<std::string> enumerants_;
  std::vector<std::string> methods_;


  void finish_decl(const kj::String& value) {
    outputLine(kj::str(kj::strArray(decl_stack_, "."),
          ".FinishDeclaration(", value, ")"));
  }

  bool post_visit_enumerant(Schema, EnumSchema::Enumerant enumerant) {
    auto line = kj::strTree(
        MODULE "Enumerant(name=\"", enumerant.getProto().getName(),
        "\", ordinal=", enumerant.getOrdinal(), get_stored_annotations(), ")");
    enumerants_.emplace_back(line.flatten().cStr());
    return false;
  }

  kj::StringTree get_stored_annotations(/*bool include_key=true*/) {
    auto stored = std::move(stored_annotations_);
    if (stored.size() > 0) {
        return kj::strTree(", annotations=", stored);
    }
    return kj::strTree("");
  }

  bool post_visit_struct_field(StructSchema, StructSchema::Field field) {
    auto decl = kj::strTree("(id=", field.getIndex(), ", name=\"",
        field.getProto().getName(), "\", type=", pop_back(last_type_),
        get_stored_annotations(), ")");
    fields_.emplace_back(decl.flatten());
    return false;
  }

  std::vector<kj::String> name_fields(std::string&& name) {
    std::vector<kj::String> fields;
    for (auto &field : fields_) {
      fields.emplace_back(kj::str(MODULE, name, field));
    }
    fields_.clear();
    return fields;
  }

  bool traverse_method(Schema schema, InterfaceSchema::Method method) override {
    auto methodProto = method.getProto();
    auto interface = schema.asInterface();
    auto proto = method.getProto();
    auto line = kj::strTree(
        MODULE "Method(id=", method.getIndex(),
        ", name=\"", proto.getName(), "\"");
    // Params
    TRAVERSE(param_list, interface, kj::str("parameters"), method.getParamType());
    line = kj::strTree(
        kj::mv(line), ", input_params=[",
        kj::strArray(name_fields("Param"), ", "), "]");

    // Results
    TRAVERSE(param_list, interface, kj::str("results"), method.getResultType());
    line = kj::strTree(
        kj::mv(line), ", output_params=[",
        kj::strArray(name_fields("Param"), ", "), "]");

    // Annotations
    TRAVERSE(annotations, schema, methodProto.getAnnotations());
    line = kj::strTree(kj::mv(line), get_stored_annotations(), ")");
    methods_.emplace_back(line.flatten().cStr());
    // printf("method %s\n", line.flatten().cStr());
    return false;
  }

  bool post_visit_annotation(schema::Annotation::Reader, Schema schema) {
    annotations_.add(kj::str(check_keyword(schema.getShortDisplayName()), "(",
          pop_back(last_value_), ")"));
    return false;
  }

  bool post_visit_annotations(Schema) {
    stored_annotations_ = kj::str("[", kj::strArray(annotations_, ", "), "]");
    annotations_.resize(0);
    return false;
  }

  bool pre_visit_type(Schema schema, schema::Type::Reader type) {
    switch (type.which()) {
      /*[[[cog
      types = ['void', 'bool', 'text', 'data', 'float32', 'float64']
      types.extend('int%s' % size for size in [8, 16, 32, 64])
      types.extend('uint%s' % size for size in [8, 16, 32, 64])
      for type in types:
        cog.outl('case schema::Type::%s:' % type.upper())
        cog.outl('  last_type_.emplace_back(kj::str(MODULE "%s"));' % type.title())
        cog.outl('  break;')
      ]]]*/
      case schema::Type::VOID:
        last_type_.emplace_back(kj::str(MODULE "Void"));
        break;
      case schema::Type::BOOL:
        last_type_.emplace_back(kj::str(MODULE "Bool"));
        break;
      case schema::Type::TEXT:
        last_type_.emplace_back(kj::str(MODULE "Text"));
        break;
      case schema::Type::DATA:
        last_type_.emplace_back(kj::str(MODULE "Data"));
        break;
      case schema::Type::FLOAT32:
        last_type_.emplace_back(kj::str(MODULE "Float32"));
        break;
      case schema::Type::FLOAT64:
        last_type_.emplace_back(kj::str(MODULE "Float64"));
        break;
      case schema::Type::INT8:
        last_type_.emplace_back(kj::str(MODULE "Int8"));
        break;
      case schema::Type::INT16:
        last_type_.emplace_back(kj::str(MODULE "Int16"));
        break;
      case schema::Type::INT32:
        last_type_.emplace_back(kj::str(MODULE "Int32"));
        break;
      case schema::Type::INT64:
        last_type_.emplace_back(kj::str(MODULE "Int64"));
        break;
      case schema::Type::UINT8:
        last_type_.emplace_back(kj::str(MODULE "Uint8"));
        break;
      case schema::Type::UINT16:
        last_type_.emplace_back(kj::str(MODULE "Uint16"));
        break;
      case schema::Type::UINT32:
        last_type_.emplace_back(kj::str(MODULE "Uint32"));
        break;
      case schema::Type::UINT64:
        last_type_.emplace_back(kj::str(MODULE "Uint64"));
        break;
      //[[[end]]]
      case schema::Type::LIST:
        TRAVERSE(type, schema, type.getList().getElementType());
        last_type_.emplace_back(kj::str("List(", pop_back(last_type_), ")"));
        break;
      case schema::Type::ENUM: {
        auto enumSchema = schemaLoader.get(
            type.getEnum().getTypeId(), type.getEnum().getBrand(), schema);
        // TODO: Deal with generics here and the below types.
        last_type_.emplace_back(kj::str(enumSchema.getShortDisplayName()));
        break;
      }
      case schema::Type::INTERFACE: {
        auto ifaceSchema = schemaLoader.get(
            type.getInterface().getTypeId(), type.getInterface().getBrand(), schema);
        last_type_.emplace_back(kj::str(ifaceSchema.getShortDisplayName()));
        break;
      }
      case schema::Type::STRUCT: {
        auto structSchema = schemaLoader.get(
            type.getStruct().getTypeId(), type.getStruct().getBrand(), schema);
        last_type_.emplace_back(kj::str(structSchema.getShortDisplayName()));
        break;
      }
      case schema::Type::ANY_POINTER:
        last_type_.emplace_back(kj::str("AnyPointer"));
        break;
    }
    return true;
  }

  bool pre_visit_value(Schema schema, schema::Type::Reader type, schema::Value::Reader value) {
    visit_value_w_type(schema, schemaLoader.getType(type, schema), value);
    return true;
  }

  void visit_value_dynamic(Schema schema, Type type, DynamicValue::Reader value) {
    // Sadly, this almost-exact-copy of visit_value_w_type is needed to deal
    // with the fact that you can't get a 'concrete' schema::Value out of a
    // List or its ilk.
    switch (type.which()) {
      /*[[[cog
      sizes32 = [8, 16, 32]
      sizes64 = [64]
      types = [
          ('bool', 'bool', 'bool'),
          ('int64', 'int64_t', 'int64'),
          ('uint64', 'uint64_t', 'uint64'),
          ('float32', 'float', 'double'),
          ('float64', 'double', 'double')
      ] + [
          ('int%d' % size, 'int%d_t' % size, 'int') for size in sizes32
      ] + [
          ('uint%d' % size, 'uint%d_t' % size, 'uint') for size in sizes32
      ] 
      for type, ctype, writer in types:
        cog.outl('case schema::Type::%s:' % type.upper())
        cog.outl('  last_value_.emplace_back(kj::str(value.as<%s>()));' % (ctype))
        cog.outl('  break;')
      ]]]*/
      case schema::Type::BOOL:
        last_value_.emplace_back(kj::str(value.as<bool>()));
        break;
      case schema::Type::INT64:
        last_value_.emplace_back(kj::str(value.as<int64_t>()));
        break;
      case schema::Type::UINT64:
        last_value_.emplace_back(kj::str(value.as<uint64_t>()));
        break;
      case schema::Type::FLOAT32:
        last_value_.emplace_back(kj::str(value.as<float>()));
        break;
      case schema::Type::FLOAT64:
        last_value_.emplace_back(kj::str(value.as<double>()));
        break;
      case schema::Type::INT8:
        last_value_.emplace_back(kj::str(value.as<int8_t>()));
        break;
      case schema::Type::INT16:
        last_value_.emplace_back(kj::str(value.as<int16_t>()));
        break;
      case schema::Type::INT32:
        last_value_.emplace_back(kj::str(value.as<int32_t>()));
        break;
      case schema::Type::UINT8:
        last_value_.emplace_back(kj::str(value.as<uint8_t>()));
        break;
      case schema::Type::UINT16:
        last_value_.emplace_back(kj::str(value.as<uint16_t>()));
        break;
      case schema::Type::UINT32:
        last_value_.emplace_back(kj::str(value.as<uint32_t>()));
        break;
      //[[[end]]]
      case schema::Type::VOID:
        last_value_.emplace_back(kj::str("value"));
        break;
      case schema::Type::TEXT:
        last_value_.emplace_back(kj::str("'", value.as<Text>(), "'"));
        break;
      case schema::Type::DATA:
        last_value_.emplace_back(kj::str("b'", value.as<Data>(), "'"));
        break;
      case schema::Type::LIST: {
        kj::Vector<kj::String> values;
        auto listType = type.asList();
        auto listValue = value.as<DynamicList>();
        for (auto element : listValue) {
          visit_value_dynamic(schema, listType.getElementType(), element);
          values.add(pop_back(last_value_));
        }
        last_value_.emplace_back(kj::str("[", kj::strArray(values, ", "), "]"));
        break;
      }
      case schema::Type::ENUM: {
        auto enumValue = value.as<DynamicEnum>();
        last_value_.emplace_back(kj::str(enumValue.getSchema().getShortDisplayName()));
        KJ_IF_MAYBE(enumerant, enumValue.getEnumerant()) {
          last_value_.emplace_back(kj::str(
              pop_back(last_value_), ".",
              check_keyword(enumerant->getProto().getName())));
        }
        break;
      }
      case schema::Type::STRUCT: {
        auto structValue = value.as<DynamicStruct>();
        kj::Vector<kj::String> items;
        for (auto field : type.asStruct().getFields()) {
          if (structValue.has(field)) {
            auto fieldValue = structValue.get(field);
            visit_value_dynamic(schema, field.getType(), fieldValue);
            items.add(kj::str("\"", field.getProto().getName(), "\": ", pop_back(last_value_)));
          }
        }
        last_value_.emplace_back(kj::str("{", kj::strArray(items, ", "), "}"));
        break;
      }
      case schema::Type::INTERFACE: {
        last_value_.emplace_back(kj::str(
            "interface? but that's not possible... how do you serialize an "
            "interface in a capnp file?"));
        break;
      }
      case schema::Type::ANY_POINTER:
        last_value_.emplace_back(kj::str(
            "any pointer? how do you serialize an anypointer in a capnp file"));
        break;
    }
  }

  void visit_value_w_type(Schema schema, Type type, schema::Value::Reader value) {
    switch (type.which()) {
      /*[[[cog
      sizes32 = [8, 16, 32]
      sizes64 = [64]
      types = {'bool': 'bool',
               'int64': 'int64', 'uint64': 'uint64',
               'float32': 'double', 'float64': 'double'}
      types.update({'int%d' % size: 'int' for size in sizes32})
      types.update({'uint%d' % size: 'uint' for size in sizes32})
      for type, writer in sorted(types.items()):
        cog.outl('case schema::Type::%s:' % type.upper())
        cog.outl('  last_value_.emplace_back(kj::str(value.get%s()));' % type.title())
        cog.outl('  break;')
      ]]]*/
      case schema::Type::BOOL:
        last_value_.emplace_back(kj::str(value.getBool()));
        break;
      case schema::Type::FLOAT32:
        last_value_.emplace_back(kj::str(value.getFloat32()));
        break;
      case schema::Type::FLOAT64:
        last_value_.emplace_back(kj::str(value.getFloat64()));
        break;
      case schema::Type::INT16:
        last_value_.emplace_back(kj::str(value.getInt16()));
        break;
      case schema::Type::INT32:
        last_value_.emplace_back(kj::str(value.getInt32()));
        break;
      case schema::Type::INT64:
        last_value_.emplace_back(kj::str(value.getInt64()));
        break;
      case schema::Type::INT8:
        last_value_.emplace_back(kj::str(value.getInt8()));
        break;
      case schema::Type::UINT16:
        last_value_.emplace_back(kj::str(value.getUint16()));
        break;
      case schema::Type::UINT32:
        last_value_.emplace_back(kj::str(value.getUint32()));
        break;
      case schema::Type::UINT64:
        last_value_.emplace_back(kj::str(value.getUint64()));
        break;
      case schema::Type::UINT8:
        last_value_.emplace_back(kj::str(value.getUint8()));
        break;
      //[[[end]]]
      case schema::Type::VOID:
        last_value_.emplace_back(kj::str("void"));
        break;
      case schema::Type::TEXT:
        last_value_.emplace_back(kj::str("'", value.getText(), "'"));
        break;
      case schema::Type::DATA:
        last_value_.emplace_back(kj::str("b'", value.getData(), "'"));
        break;
      case schema::Type::LIST: {
        kj::Vector<kj::String> values;
        auto listType = type.asList();
        auto listValue = value.getList().getAs<DynamicList>(listType);
        for (auto element : listValue) {
          visit_value_dynamic(schema, listType.getElementType(), element);
          values.add(pop_back(last_value_));
        }
        last_value_.emplace_back(kj::str("[", kj::strArray(values, ", "), "]"));
        break;
      }
      case schema::Type::ENUM: {
        auto enumerants = type.asEnum().getEnumerants();
        last_value_.emplace_back(kj::str(type.asEnum().getShortDisplayName()));
        for (auto enumerant : enumerants) {
          if (enumerant.getIndex() == value.getEnum()) {
            last_value_.emplace_back(kj::str(
                pop_back(last_value_), ".", enumerant.getProto().getName()));
            break;
          }
        }
        break;
      }
      case schema::Type::STRUCT: {
        auto structValue = value.getStruct().getAs<DynamicStruct>(type.asStruct());
        kj::Vector<kj::String> items;
        for (auto field : type.asStruct().getFields()) {
          if (structValue.has(field)) {
            auto fieldValue = structValue.get(field);
            visit_value_dynamic(schema, field.getType(), fieldValue);
            items.add(kj::str("\"", field.getProto().getName(), "\": ", pop_back(last_value_)));
          }
        }
        last_value_.emplace_back(kj::str("{", kj::strArray(items, ", "), "}"));
        break;
      }
      case schema::Type::INTERFACE: {
        last_value_.emplace_back(kj::str(
            "interface? but that's not possible... how do you serialize an "
            "interface in a capnp file?"));
        break;
      }
      case schema::Type::ANY_POINTER: {
        last_value_.emplace_back(kj::str(
            "any pointer? how do you serialize an anypointer in a capnp file"));
        break;
      }
    }
  }

};

constexpr const char CapnpcCara::FILE_SUFFIX[];

KJ_MAIN(CapnpcGenericMain<CapnpcCara>);
