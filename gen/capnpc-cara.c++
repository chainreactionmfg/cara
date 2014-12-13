#include <algorithm>
#include <map>
#include <memory>
#include <regex>
#include <set>
#include <stack>
#include <unordered_set>
#include <vector>
#include "generic.h"

#define MODULE_NAME "cara"
#define MODULE MODULE_NAME "."

// 'typedef' some long types.
using NestedNode = schema::Node::NestedNode::Reader;
using RequestedFile = schema::CodeGeneratorRequest::RequestedFile::Reader;

const char FILE_SUFFIX[] = ".py";
const std::regex PYTHON_NAME_INVALID_CHARS_RE {R"([^A-Za-z_]|[^\w])"};


typedef std::stack<kj::String, std::vector<kj::String>> string_stack;
kj::String pop_back(string_stack& vect) {
  kj::String result = kj::str(vect.top());
  vect.pop();
  return result;
}

template <typename T>
kj::String to_py_array(T&& arr) {
  return kj::str("[", kj::strArray(arr, ", "), "]");
}

struct StringWithId {
  uint id;
  kj::String data;
  friend bool operator<(const StringWithId& a, const StringWithId& b) {
    return a.id < b.id;
  }
};

std::vector<kj::String> to_sorted_vector(std::vector<StringWithId>& vec) {
  std::sort(vec.begin(), vec.end());
  std::vector<kj::String> result;
  for ( auto& obj : vec) {
    result.emplace_back(kj::str(obj.data));
  }
  return result;
}

template <typename T> using hash_set = std::unordered_set<T>;

/*[[[cog
import textwrap
wrapper = textwrap.TextWrapper(
    width=80, initial_indent='  ', subsequent_indent='  ')
keyword_list = ', '.join('"%s"' % kw for kw in python_keywords)
cog.outl('const hash_set<std::string> KEYWORDS = {')
for line in wrapper.wrap('%s' % keyword_list):
  cog.outl(line)
cog.outl('};')
]]]*/
const hash_set<std::string> KEYWORDS = {
  "and", "as", "assert", "break", "class", "continue", "def", "del", "elif",
  "else", "except", "exec", "finally", "for", "from", "global", "if", "import",
  "in", "is", "lambda", "not", "or", "pass", "print", "raise", "return", "try",
  "while", "with", "yield"
};
//[[[end]]]
template<typename T>
kj::String check_keyword(T&& input) {
  kj::String output = kj::str(kj::mv(input));
  // Append a _ for keywords.
  if (KEYWORDS.count(output.cStr()))
    output = kj::str(kj::mv(output), "_");

  /*[[[cog
  import string
  char_map = []  # {'+': 'x'}
  for i in range(256):
    ch = chr(i)
    # Map + to x
    if ch == '+':
      char_map.append('x')
    # Map [^\w_] to _
    elif ch not in string.ascii_letters + string.digits + '.':
      char_map.append('_')
    else:
      char_map.append(ch)
  cog.outl('static const char char_map[256] {')
  line = ', '.join("'%s'" % ch for ch in char_map)
  wrapper = textwrap.TextWrapper(
      width=78, initial_indent='  ', subsequent_indent='  ')
  for line in wrapper.wrap(line):
    cog.outl(line)
  cog.outl('};')
  ]]]*/
  static const char char_map[256] {
    '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_',
    '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_',
    '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', 'x', '_',
    '_', '.', '_', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '_', '_',
    '_', '_', '_', '_', '_', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
    'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y',
    'Z', '_', '_', '_', '_', '_', '_', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h',
    'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w',
    'x', 'y', 'z', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_',
    '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_',
    '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_',
    '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_',
    '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_',
    '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_',
    '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_',
    '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_',
    '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_', '_',
    '_'
  };
  ///[[[end]]]
  // Replace invalid characters with _ or a known character.
  std::string newFilenameStr = output.cStr();
  std::sregex_iterator iter {
    newFilenameStr.begin(), newFilenameStr.end(), 
      PYTHON_NAME_INVALID_CHARS_RE};
  std::sregex_iterator end;
  bool prepend = false;
  for (; iter != end; ++iter) {
    // all results will be a single character
    auto match = iter->str()[0];
    auto pos = iter->position();
    if (pos == 0) {
      // If it's at the beginning, don't make it start with _.
      prepend = true;
    }
    newFilenameStr[pos] = char_map[(int)match];
  }
  if (prepend) {
    newFilenameStr.insert(newFilenameStr.begin(), 'V');
  }
  return kj::str(newFilenameStr);
}

template<typename T>
kj::String clean_filename(T&& filename, bool last=true) {
  kj::String newFilename = kj::str(filename);
  // Cut off first/last period.
  auto found = last ? filename.findLast('.') : filename.findFirst('.');
  KJ_IF_MAYBE(loc, found) {
    newFilename = kj::str(filename.slice(0, *loc));
  }
  return check_keyword(kj::mv(newFilename));
}

class BasePythonGenerator : public BaseGenerator {
 public:
  BasePythonGenerator(SchemaLoader& loader)
    : BaseGenerator(loader) {}

 protected:
  std::vector<StringWithId> fields_;
  std::vector<StringWithId> enumerants_;
  std::vector<StringWithId> methods_;

  string_stack last_type_;
  string_stack last_value_;

  kj::Vector<kj::String> annotations_;
  kj::String stored_annotations_ = kj::str("");

  std::vector<unsigned long> importIds_;

  kj::String display_name(Schema& schema) {
    auto&& proto = schema.getProto();
    kj::String name = kj::str(proto.getDisplayName());
    name = kj::str(name.slice(name.findFirst(':').orDefault(-1) + 1));

    auto is_import = [this] (auto id) {
      return (
          std::find(importIds_.begin(), importIds_.end(), id)
          != importIds_.end());
    };
    auto scopeId = proto.getScopeId();
    while (scopeId != 0) {
      proto = schemaLoader.get(scopeId).getProto();
      if (is_import(scopeId)) {
        auto fn = kj::str(proto.getDisplayName());
        fn = clean_filename(fn.slice(fn.findFirst('/').orDefault(-1) + 1));
        name = kj::str(fn, ".", kj::mv(name));
      }
      scopeId = proto.getScopeId();
    }
    return name;
  }

  kj::String get_fields(std::string&& name) {
    std::vector<kj::String> fields;
    using field_type = decltype(*fields_.begin());
    std::sort(fields_.begin(), fields_.end());
    for (auto &field : fields_) {
      fields.emplace_back(kj::str(MODULE, name, field.data));
    }
    fields_.clear();
    return to_py_array(fields);
  }

  kj::StringTree get_stored_annotations() {
    auto stored = std::move(stored_annotations_);
    if (stored.size() > 0) {
        return kj::strTree(", annotations=", stored);
    }
    return kj::strTree("");
  }

  bool pre_visit_import(Schema, Import::Reader import) override {
    importIds_.emplace_back(import.getId());
    return false;
  }

  bool post_visit_annotation(schema::Annotation::Reader, Schema schema) {
    annotations_.add(kj::str(check_keyword(display_name(schema)), "(",
          pop_back(last_value_), ")"));
    return false;
  }

  bool post_visit_annotations(Schema) {
    stored_annotations_ = to_py_array(annotations_);
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
        cog.outl('  last_type_.push(kj::str(MODULE "%s"));' % type.title())
        cog.outl('  break;')
      ]]]*/
      case schema::Type::VOID:
        last_type_.push(kj::str(MODULE "Void"));
        break;
      case schema::Type::BOOL:
        last_type_.push(kj::str(MODULE "Bool"));
        break;
      case schema::Type::TEXT:
        last_type_.push(kj::str(MODULE "Text"));
        break;
      case schema::Type::DATA:
        last_type_.push(kj::str(MODULE "Data"));
        break;
      case schema::Type::FLOAT32:
        last_type_.push(kj::str(MODULE "Float32"));
        break;
      case schema::Type::FLOAT64:
        last_type_.push(kj::str(MODULE "Float64"));
        break;
      case schema::Type::INT8:
        last_type_.push(kj::str(MODULE "Int8"));
        break;
      case schema::Type::INT16:
        last_type_.push(kj::str(MODULE "Int16"));
        break;
      case schema::Type::INT32:
        last_type_.push(kj::str(MODULE "Int32"));
        break;
      case schema::Type::INT64:
        last_type_.push(kj::str(MODULE "Int64"));
        break;
      case schema::Type::UINT8:
        last_type_.push(kj::str(MODULE "Uint8"));
        break;
      case schema::Type::UINT16:
        last_type_.push(kj::str(MODULE "Uint16"));
        break;
      case schema::Type::UINT32:
        last_type_.push(kj::str(MODULE "Uint32"));
        break;
      case schema::Type::UINT64:
        last_type_.push(kj::str(MODULE "Uint64"));
        break;
      //[[[end]]]
      case schema::Type::LIST:
        TRAVERSE(type, schema, type.getList().getElementType());
        last_type_.push(kj::str(MODULE "List(", pop_back(last_type_), ")"));
        break;
      case schema::Type::ENUM: {
        auto enumSchema = schemaLoader.get(
            type.getEnum().getTypeId(), type.getEnum().getBrand(), schema);
        // TODO: Deal with generics here and the below types.
        last_type_.push(kj::str(display_name(enumSchema)));
        break;
      }
      case schema::Type::INTERFACE: {
        auto ifaceSchema = schemaLoader.get(
            type.getInterface().getTypeId(), type.getInterface().getBrand(),
            schema);
        last_type_.push(kj::str(display_name(ifaceSchema)));
        break;
      }
      case schema::Type::STRUCT: {
        auto structSchema = schemaLoader.get(
            type.getStruct().getTypeId(), type.getStruct().getBrand(), schema);
        last_type_.push(kj::str(display_name(structSchema)));
        break;
      }
      case schema::Type::ANY_POINTER:
        last_type_.push(kj::str(MODULE "AnyPointer"));
        break;
    }
    return true;
  }

  bool pre_visit_dynamic_value(
      Schema schema, Type type, DynamicValue::Reader value) {
    auto convertFloat = [this] (auto floatVal) {
      if (std::isinf(floatVal)) {
        if (floatVal > 0) {
          last_value_.push(kj::str(R"(float("inf"))"));
        } else {
          last_value_.push(kj::str(R"(float("-inf"))"));
        }
      } else if (std::isnan(floatVal)) {
        last_value_.push(kj::str(R"(float("nan"))"));
      } else {
        last_value_.push(kj::str(floatVal));
      }
    };
    switch (type.which()) {
      /*[[[cog
      sizes32 = [8, 16, 32]
      sizes64 = [64]
      types = [
          ('int64', 'int64_t', 'int64'),
          ('uint64', 'uint64_t', 'uint64'),
      ] + [
          ('int%d' % size, 'int%d_t' % size, 'int') for size in sizes32
      ] + [
          ('uint%d' % size, 'uint%d_t' % size, 'uint') for size in sizes32
      ] 
      for type, ctype, writer in types:
        cog.outl('case schema::Type::%s:' % type.upper())
        cog.outl('  last_value_.push(kj::str(value.as<%s>()));' % (ctype))
        cog.outl('  break;')
      ]]]*/
      case schema::Type::INT64:
        last_value_.push(kj::str(value.as<int64_t>()));
        break;
      case schema::Type::UINT64:
        last_value_.push(kj::str(value.as<uint64_t>()));
        break;
      case schema::Type::INT8:
        last_value_.push(kj::str(value.as<int8_t>()));
        break;
      case schema::Type::INT16:
        last_value_.push(kj::str(value.as<int16_t>()));
        break;
      case schema::Type::INT32:
        last_value_.push(kj::str(value.as<int32_t>()));
        break;
      case schema::Type::UINT8:
        last_value_.push(kj::str(value.as<uint8_t>()));
        break;
      case schema::Type::UINT16:
        last_value_.push(kj::str(value.as<uint16_t>()));
        break;
      case schema::Type::UINT32:
        last_value_.push(kj::str(value.as<uint32_t>()));
        break;
      //[[[end]]]
      case schema::Type::VOID:
        last_value_.push(kj::str(MODULE "Void()"));
        break;
      case schema::Type::BOOL:
        last_value_.push(kj::str(value.as<bool>() ? "True" : "False"));
        break;
      case schema::Type::FLOAT32:
        convertFloat(value.as<float>());
        break;
      case schema::Type::FLOAT64:
        convertFloat(value.as<double>());
        break;
      case schema::Type::TEXT:
        last_value_.push(kj::str("'", value.as<Text>(), "'"));
        break;
      case schema::Type::DATA:
        last_value_.push(kj::str("b'", value.as<Data>(), "'"));
        break;
      case schema::Type::LIST: {
        kj::Vector<kj::String> values;
        auto listType = type.asList();
        auto listValue = value.as<DynamicList>();
        for (auto element : listValue) {
          TRAVERSE(dynamic_value, schema, listType.getElementType(), element);
          values.add(pop_back(last_value_));
        }
        last_value_.push(to_py_array(values));
        return true;
      }
      case schema::Type::ENUM: {
        auto enumValue = value.as<DynamicEnum>();
        auto schema = enumValue.getSchema().getGeneric();
        last_value_.push(kj::str(display_name(schema)));
        KJ_IF_MAYBE(enumerant, enumValue.getEnumerant()) {
          last_value_.push(kj::str(
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
            TRAVERSE(dynamic_value, schema, field.getType(), fieldValue);
            items.add(kj::str("\"", field.getProto().getName(), "\": ",
                              pop_back(last_value_)));
          }
        }
        last_value_.push(kj::str("{", kj::strArray(items, ", "), "}"));
        return true;
      }
      case schema::Type::INTERFACE: {
        last_value_.push(kj::str(
            "interface? but that's not possible... how do you serialize an "
            "interface in a capnp file?"));
        break;
      }
      case schema::Type::ANY_POINTER:
        last_value_.push(kj::str(
            "any pointer? how do you serialize an anypointer in a capnp file"));
        break;
    }
    return false;
  }

  bool post_visit_enumerant(Schema, EnumSchema::Enumerant enumerant) {
    enumerants_.emplace_back(StringWithId {enumerant.getOrdinal(), kj::str(
        MODULE "Enumerant(name=\"", enumerant.getProto().getName(),
        "\", ordinal=", enumerant.getOrdinal(), get_stored_annotations(),
        ")")});
    return false;
  }

  bool post_visit_struct_field_slot(StructSchema, StructSchema::Field field, schema::Field::Slot::Reader) {
    fields_.emplace_back(StringWithId {field.getIndex(), kj::str("(id=",
          field.getIndex(), ", name=\"", field.getProto().getName(),
          "\", type=", pop_back(last_type_), get_stored_annotations(), ")")});
    return false;
  }

  bool traverse_method(Schema schema, InterfaceSchema::Method method) override {
    auto methodProto = method.getProto();
    auto interface = schema.asInterface();
    auto proto = method.getProto();
    auto line = kj::strTree(
        MODULE "Method(id=", method.getIndex(),
        ", name=\"", proto.getName(), "\"");
    // Params
    TRAVERSE(param_list, interface, kj::str("_"), method.getParamType());
    line = kj::strTree(
        kj::mv(line), ", input_params=", get_fields("Param"));

    // Results
    TRAVERSE(param_list, interface, kj::str("_"), method.getResultType());
    line = kj::strTree(
        kj::mv(line), ", output_params=", get_fields("Param"));

    // Annotations
    TRAVERSE(annotations, schema, methodProto.getAnnotations());
    line = kj::strTree(kj::mv(line), get_stored_annotations(), ")");
    methods_.emplace_back(StringWithId {method.getIndex(), line.flatten()});
    return false;
  }

};

class EnumForwardDecl : public BasePythonGenerator {
  // This is separate because normal forward declaration and finishing causes
  // enums to be dirty. They at least need their enumerants in their forward
  // declaration, the annotations of the enum and its members can come later.

 public:
  EnumForwardDecl(
      SchemaLoader& loader, FILE* fd,
      std::vector<std::string> decl_stack)
    : BasePythonGenerator(loader),
      fd_(fd),
      decl_stack_(decl_stack) {}
 private:
  FILE* fd_;
  std::vector<std::string> decl_stack_;
  bool post_visit_enum_decl(Schema, NestedNode decl) {
    fprintf(
        fd_, "%s = " MODULE "Enum(name=\"%s\", enumerants=%s)\n",
        kj::strArray(decl_stack_, ".").cStr(), decl.getName().cStr(),
        to_py_array(to_sorted_vector(enumerants_)).cStr());
    return false;
  }

  bool post_visit_annotations(Schema) {
    // Ignore all annotations for enum forward decls, they'll show up again
    // when we need them.
    annotations_.resize(0);
    return false;
  }

};

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

  bool pre_visit_import(Schema, Import::Reader import) override {
    auto path = import.getName();
    bool root = path.startsWith("/");
    if (root) path = path.slice(1);

    std::vector<std::string> importPath;
    if (root) {
      importPath.emplace_back(MODULE_NAME);
    }
    std::string pathStr {import.getName().slice(root ? 1 : 0).cStr()};
    std::stringstream pathStream {pathStr};
    for (std::string tmp; std::getline(pathStream, tmp, '/');) {
      importPath.emplace_back(clean_filename(kj::str(tmp)).cStr());
    }
    auto name = std::string(importPath.back());
    importPath.pop_back();

    if (importPath.size() == 0) {
      fprintf(fd_, "import %s\n", name.c_str());
    } else {
      fprintf(
          fd_, "from %s import %s\n",
          kj::strArray(importPath, ".").cStr(),
          name.c_str());
    }
    return false;
  }

  bool pre_visit_decl(Schema, NestedNode decl) {
    decl_stack_.emplace_back(check_keyword(decl.getName()).cStr());
    return false;
  }

  bool post_visit_decl(Schema, NestedNode) {
    decl_stack_.pop_back();
    return false;
  }

  bool pre_visit_enum_decl(Schema schema, NestedNode decl) {
    // Output all the fields of the enum in the forward decl.
    EnumForwardDecl enumDecl {schemaLoader, fd_, decl_stack_};
    enumDecl.traverse_enum_decl(schema, decl);
    return false;
  }
  /*[[[cog
  decls = ['const', 'annotation', 'struct', 'interface']
  for decl in decls:
    cog.outl('bool pre_visit_%s_decl(Schema, NestedNode decl) {' % decl)
    cog.outl('  outputDecl("%s", decl.getName());' % decl.title())
    cog.outl('  return false;')
    cog.outl('}')
  ]]]*/
  bool pre_visit_const_decl(Schema, NestedNode decl) {
    outputDecl("Const", decl.getName());
    return false;
  }
  bool pre_visit_annotation_decl(Schema, NestedNode decl) {
    outputDecl("Annotation", decl.getName());
    return false;
  }
  bool pre_visit_struct_decl(Schema, NestedNode decl) {
    outputDecl("Struct", decl.getName());
    return false;
  }
  bool pre_visit_interface_decl(Schema, NestedNode decl) {
    outputDecl("Interface", decl.getName());
    return false;
  }
  //[[[end]]]
};

class CapnpcCara : public BasePythonGenerator {
 public:
  CapnpcCara(SchemaLoader& loader)
    : BasePythonGenerator(loader) {}
 private:
  FILE* fd_;
  std::vector<std::string> decl_stack_;

  bool pre_visit_file(Schema schema, RequestedFile requestedFile) override {
    auto inputFilename = requestedFile.getFilename();
    kj::String outputFilename = kj::str(clean_filename(inputFilename), FILE_SUFFIX);
    fd_ = fopen(outputFilename.cStr(), "w");

    // Start the file
    outputLine("from " MODULE_NAME " import " MODULE_NAME);
    outputLine("");
    outputLine("# Forward declarations:");

    // Output 'forward decls' first.
    CapnpcCaraForwardDecls decls(schemaLoader, fd_);
    decls.traverse_file(schema, requestedFile);
    outputLine("");
    outputLine("# Finishing declarations:");
    return false;
  }

  bool post_visit_file(Schema, RequestedFile) override {
    fclose(fd_);
    return false;
  }

  void outputLine(kj::StringPtr line) {
    fprintf(fd_, "%s\n", line.cStr());
  }

  bool pre_visit_decl(Schema, NestedNode decl) {
    decl_stack_.emplace_back(check_keyword(decl.getName()).cStr());
    return false;
  }

  bool post_visit_decl(Schema, NestedNode) {
    decl_stack_.pop_back();
    return false;
  }

  bool post_visit_const_decl(Schema, NestedNode) {
    finish_decl("type=", pop_back(last_type_),
          ", value=", pop_back(last_value_), get_stored_annotations());
    return false;
  }

  bool post_visit_struct_decl(Schema, NestedNode) {
    finish_decl(
        "fields=", get_fields("Field"), get_stored_annotations());
    return false;
  }

  bool post_visit_interface_decl(Schema schema, NestedNode) {
    kj::Vector<kj::String> supers;
    for (auto super : schema.asInterface().getSuperclasses()) {
      supers.add(kj::str(display_name(super)));
    }
    finish_decl("superclasses=[", kj::strArray(supers, ", "), "], methods=",
        to_py_array(to_sorted_vector(methods_)), get_stored_annotations());
    methods_.clear();
    return false;
  }

  bool post_visit_annotation_decl(Schema schema, NestedNode) {
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
    auto line = kj::strTree("type=", pop_back(last_type_), ", applies_to=");
    if (count == NUM_TARGETS) {
      // Then if it matches everything, use Annotation.all
      line = kj::strTree(kj::mv(line), MODULE "Annotation.ALL");
    } else {
      // Otherwise, output each target.
      line = kj::strTree(kj::mv(line), to_py_array(targets));
    }
    line = kj::strTree(kj::mv(line), get_stored_annotations());
    finish_decl(line);
    return false;
  }

  bool post_visit_enum_decl(Schema, NestedNode) {
    finish_decl(
        "enumerants=", to_py_array(to_sorted_vector(enumerants_)),
        get_stored_annotations());
    enumerants_.clear();
    return false;
  }

  template<typename... Args>
  void finish_decl(Args&&... args) {
    kj::String start = kj::str(kj::strArray(decl_stack_, "."),
          ".FinishDeclaration(");
    kj::String end = kj::str(std::forward<Args>(args)..., ")");
    if (end.size() + start.size() >= 80) {
      start = kj::str(kj::mv(start), "\n    ");
    }
    outputLine(kj::str(start, end));
  }

};

KJ_MAIN(CapnpcGenericMain<CapnpcCara>);
