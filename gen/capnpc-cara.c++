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
  template<typename T>
  void outputDecl(std::string&& type, T&& name) {
    fprintf(
        fd_, "%s = " MODULE "%s(name=\"%s\")\n",
        check_keyword(name).cStr(), type.c_str(), name.cStr());
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

class CapnpcPython : public BaseGenerator {
 public:
  CapnpcPython(SchemaLoader &schemaLoader)
      : BaseGenerator(schemaLoader) {
    start_decl("", "");
  }

 private:
  constexpr static const char FILE_SUFFIX[] = ".py";
  FILE* fd_;
  kj::String last_type_;
  kj::String last_value_;
  struct FieldInfo {
    kj::String name, params;
    hash_set<std::string> needed_names;
  };
  std::vector<FieldInfo> fields_;
  // bool output_struct_fields_ = true;
  // kj::Vector<kj::String> param_list_;
  kj::Vector<kj::String> annotations_;
  kj::String stored_annotations_ = kj::str("");

  // Stack of declarations
  struct LineInfo {
    std::string name, value;
    hash_set<std::string> needed_names;
  };
  struct DeclInfo {
    std::string name, base;
    hash_set<std::string> defined_names;
    // std::vector<LineInfo> lines;
    std::vector<DeclInfo> sub_decls;
    // std::vector<LineInfo> orphans;
    Indent indent;
  };
  std::vector<DeclInfo> decls_;

  // More specific decl infos
  struct EnumerantInfo {
    // std::string name, ordinal;
    // kj::Vector<kj::String> annotations;
    std::string enumerant;
    hash_set<std::string> needed_names;
  };
  std::vector<EnumerantInfo> enumerants_;
  struct MethodInfo {
    std::string method;
    hash_set<std::string> needed_names;
  };
  std::vector<MethodInfo> methods_;

  // names 'defined' in the class
  // hash_set<std::string> defined_names_;
  hash_set<std::string> needed_names_;

  bool pre_visit_file(Schema schema, schema::CodeGeneratorRequest::RequestedFile::Reader requestedFile) override {
    kj::String outputFilename;
    auto inputFilename = requestedFile.getFilename();
    KJ_IF_MAYBE(loc, inputFilename.findLast('.')) {
      outputFilename = kj::str(inputFilename.slice(0, *loc), FILE_SUFFIX);
    } else {
      outputFilename = kj::str(inputFilename, FILE_SUFFIX);
    }
    fd_ = fopen(outputFilename.cStr(), "w");
    indent_ = Indent(0);

    CapnpcCaraForwardDecls decls(schemaLoader, fd_);
    decls.traverse_file(schema, requestedFile);
    fclose(fd_);
    return true;


    outputLine("import " MODULE_NAME);
    return false;
  }

  bool post_visit_file(Schema, schema::CodeGeneratorRequest::RequestedFile::Reader) override {
    fclose(fd_);
    return false;
  }

  Indent indent_;
  uint outputted_lines_;
  void outputIndent() {
    outputted_lines_++;
    for (auto ch : indent_) {
      fputc(ch, fd_);
    }
  }


  void outputLine(kj::StringPtr line) {
    outputIndent();
    fwrite(line.cStr(), line.size(), 1, fd_);
    fputc('\n', fd_);
  }

  /*[[[cog
  def start_decl(base):
    method = base.lower() + '_decl'
    args = list(visit_methods[method])
    # name the decl argument appropriately.
    for i, arg in enumerate(args):
      if arg == 'schema::Node::NestedNode::Reader':
        args[i] = arg + ' decl'
    cog.outl('bool pre_visit_%s(%s) {' % (method, ', '.join(args)))
    cog.outl('  start_decl(decl.getName().cStr(), "%s");' % base.title())
    cog.outl('  return false;')
    cog.outl('}')
  def finish_decl(base):
    method = base.lower() + '_decl'
    cog.outl('bool post_visit_%s_decl(%s) {' % (base, ', '.join(visit_methods[method])))
    cog.outl('  finish_decl();')
    cog.outl('  return false;')
    cog.outl('}')
  def decl(*bases):
    for base in bases:
      start_decl(base)
      finish_decl(base)
  ]]]*/
  //[[[end]]]

  bool post_visit_const_decl(Schema, schema::Node::NestedNode::Reader decl) {
    define_name(kj::str(decl.getName().cStr()), kj::str(MODULE "Const(name=\"", decl.getName(),
        "\", type=", last_type_, ", value=", last_value_,
        get_stored_annotations(), ")"));
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
      cog.outl('  count += 1;')
      cog.outl('  targets.add(kj::str("\\"%s\\""));' % target)
      cog.outl('}')
      # Then if it matches everything, use Annotation.all
      # Otherwise, add each one to the line and count--
      # Only output an extra , if count > 0.
    ]]]*/
    static const int NUM_TARGETS = 13;
    if (proto.getTargetsStruct()) {
      count += 1;
      targets.add(kj::str("\"struct\""));
    }
    if (proto.getTargetsInterface()) {
      count += 1;
      targets.add(kj::str("\"interface\""));
    }
    if (proto.getTargetsGroup()) {
      count += 1;
      targets.add(kj::str("\"group\""));
    }
    if (proto.getTargetsEnum()) {
      count += 1;
      targets.add(kj::str("\"enum\""));
    }
    if (proto.getTargetsFile()) {
      count += 1;
      targets.add(kj::str("\"file\""));
    }
    if (proto.getTargetsField()) {
      count += 1;
      targets.add(kj::str("\"field\""));
    }
    if (proto.getTargetsUnion()) {
      count += 1;
      targets.add(kj::str("\"union\""));
    }
    if (proto.getTargetsGroup()) {
      count += 1;
      targets.add(kj::str("\"group\""));
    }
    if (proto.getTargetsEnumerant()) {
      count += 1;
      targets.add(kj::str("\"enumerant\""));
    }
    if (proto.getTargetsAnnotation()) {
      count += 1;
      targets.add(kj::str("\"annotation\""));
    }
    if (proto.getTargetsConst()) {
      count += 1;
      targets.add(kj::str("\"const\""));
    }
    if (proto.getTargetsParam()) {
      count += 1;
      targets.add(kj::str("\"param\""));
    }
    if (proto.getTargetsMethod()) {
      count += 1;
      targets.add(kj::str("\"method\""));
    }
    //[[[end]]]
    auto line = kj::strTree(
          MODULE "Annotation(name=\"", decl.getName(), "\", applies_to=");
    if (count == NUM_TARGETS) {
      line = kj::strTree(kj::mv(line), MODULE "Annotation.ALL");
    } else {
      line = kj::strTree(kj::mv(line), "[", kj::strArray(targets, ", "), "]");
    }
    // Special case annotations on annotations.
    // traverse_annotations(schema);
    line = kj::strTree(kj::mv(line), get_stored_annotations());
    // TRAVERSE(type, schema, schema.getProto().getAnnotation().getType());
    line = kj::strTree(kj::mv(line), ", type=", last_type_, ")");
    define_name(kj::str(decl.getName()), line.flatten());
    return false;
  }

  void start_decl(std::string&& name, std::string&& base) {
    // push onto the stack.
    decls_.emplace_back(DeclInfo {name, base, hash_set<std::string> {}, {}, Indent(decls_.size())});
    fflush(stdout);
  }

  void finish_decl() {
    // printf("last decl? %zu\n", decls_.size());
    auto back = std::move(decls_.back());
    decls_.pop_back();
    if (decls_.size() == 1) {
      // Last decl, so print it out.
      indent_ = Indent(0);
      print_decl(back, decls_.back());
      // printf("last decl\n");
    } else {
      // Push it onto the parent decl instead.
      decls_.back().sub_decls.emplace_back(back);
    }
    // print_orphans(decls_.back());
  }

  // void print_orphans(DeclInfo& decl) {
  //   while (1) {
  //     size_t num_defined_names = decl.defined_names.size();
  //     printf("orphan count %s -- %zu\n", decl.name.c_str(), decl.orphans.size());
  //     // Attempt to print out orphans immediately?
  //     for (auto it = decl.orphans.begin(); it != decl.orphans.end(); ++it) {
  //       printf("orphan from %s: %s = %s\n", decl.name.c_str(), it->name.c_str(), it->value.c_str());
  //       if (needed_names_defined(decl, it->needed_names)) {
  //         print_line(decl, *it);
  //         it = decl.orphans.erase(it);
  //       }
  //     }
  //     if (num_defined_names == decl.defined_names.size()) {
  //       // No new names, stop looping.
  //       return;
  //     }
  //     // New names defined, look for new orphans to print out!
  //   }
  // }

  bool needed_names_defined(DeclInfo& decl, hash_set<std::string> needed_names) {
    for (auto& name : needed_names) {
      printf("checking if %s is in %s\n", name.c_str(), decl.name.c_str());
      // printf("%s needs %s\n", line.name.c_str(), name.c_str());
      if (decl.defined_names.count(name) == 0 && decls_[0].defined_names.count(name) == 0) {
        // printf("undefined name: %s\n", name.c_str());
        return false;
      }
    }
    return true;
  }

  // void move_orphans(DeclInfo& back, DeclInfo& parent) {
  //   printf("orphan count %s : %zu\n", back.name.c_str(), back.orphans.size());
  //   for (auto& orphan : back.orphans) {
  //     printf("\nmoving orphan %s: %s\n\n", back.name.c_str(), orphan.name.c_str());
  //     orphan.name = back.name + "." + orphan.name;
  //     parent.orphans.emplace_back(orphan);
  //   }
  // }

  void print_decl(DeclInfo& decl, DeclInfo& parent) {
    outputLine(kj::str("@" MODULE "define"));
    outputLine(kj::str("def ", check_keyword(decl.name), "():"));
    // MODULE, decl.base, "):"));
    ++indent_;
    outputted_lines_ = 0;
    // now output sub-decls
    for (auto& sub_decl : decl.sub_decls) {
      print_decl(sub_decl, decl);
    }
    // and now our own definitions
    // for (auto& line : decl.lines) {
    //   print_line(decl, line);
    // }
    if (outputted_lines_ == 0) {
      outputLine(kj::str("return ", decl.base, "(name=\"", decl.name, "\")"));
    }
    --indent_;
    printf("defining %s inside %s\n", decl.name.c_str(), parent.name.c_str());
    parent.defined_names.emplace(decl.name);
    // move_orphans(decl, parent);
    // print_orphans(decl);
  }

  void print_line(DeclInfo& decl, LineInfo& line) {
    if (!needed_names_defined(decl, line.needed_names)) {
      printf("print -- %s doesn't have %s\n", line.name.c_str(), stringify(line.needed_names).c_str());
      // decl.orphans.emplace_back(line);
      return;
    }
    outputLine(kj::str(check_keyword(line.name), " = ", line.value));
    if (decls_.size() == 1) {
      decl.defined_names.emplace(line.name);
    }
  }

  void define_name(const kj::String& name, const kj::String& value,
      decltype(needed_names_) needed_names = decltype(needed_names_) {}) {
    if (needed_names.size() == 0) {
      needed_names = std::move(needed_names_);
    }
    /*
     *printf("defining %s as %s and needing %s\n", name.cStr(), value.cStr(),
     *    stringify(needed_names).c_str());
     */
    auto line = LineInfo {name.cStr(), value.cStr(), needed_names};
    if (decls_.size() == 1) {
      print_line(decls_.back(), line);
      // print_orphans(decls_.back());
    } else {
      // decls_.back().lines.emplace_back(line);
    }
  }

  bool post_visit_enumerant(Schema, EnumSchema::Enumerant enumerant) {
    auto line = kj::strTree(
        MODULE "Enumerant(name=\"", enumerant.getProto().getName(),
        "\", ordinal=", enumerant.getOrdinal(), get_stored_annotations(), ")");
    enumerants_.emplace_back(EnumerantInfo {line.flatten().cStr(), needed_names_});
    return false;
  }

  /*[[[cog decl('struct', 'enum', 'interface') ]]]*/
  bool pre_visit_struct_decl(Schema, schema::Node::NestedNode::Reader decl) {
    start_decl(decl.getName().cStr(), "Struct");
    return false;
  }
  bool post_visit_struct_decl(Schema, schema::Node::NestedNode::Reader) {
    finish_decl();
    return false;
  }
  bool pre_visit_enum_decl(Schema, schema::Node::NestedNode::Reader decl) {
    start_decl(decl.getName().cStr(), "Enum");
    return false;
  }
  bool post_visit_enum_decl(Schema, schema::Node::NestedNode::Reader) {
    finish_decl();
    return false;
  }
  bool pre_visit_interface_decl(Schema, schema::Node::NestedNode::Reader decl) {
    start_decl(decl.getName().cStr(), "Interface");
    return false;
  }
  bool post_visit_interface_decl(Schema, schema::Node::NestedNode::Reader) {
    finish_decl();
    return false;
  }
  //[[[end]]]
  
  kj::StringTree get_stored_annotations(/*bool include_key=true*/) {
    if (stored_annotations_.size() > 0) {
        return kj::strTree(", annotations=", stored_annotations_);
    }
    return kj::strTree("");
  }

  bool post_visit_struct_field(StructSchema, StructSchema::Field field) {
    auto name = check_keyword(field.getProto().getName());
    auto decl = kj::strTree("(id=", field.getIndex(), ", name=\"",
        field.getProto().getName(), "\", type=", last_type_,
        get_stored_annotations(), ")");
    fields_.emplace_back(FieldInfo {kj::mv(name), decl.flatten(), kj::mv(needed_names_)});
    return false;
  }

  // bool post_visit_struct_fields(StructSchema) {
  //   param_list_.resize(0);
  //   for (auto& field : last_fields_) {
  //     if (output_struct_fields_) {
  //       define_name(field.name, kj::str(MODULE "Field", field.params), field.needed_names);
  //     } else {
  //       param_list_.add(kj::str(MODULE "Param", field.params));
  //     }
  //   }
  //   fields_.clear();
  //   return false;
  // }

  bool traverse_method(Schema schema, InterfaceSchema::Method method) override {
    auto methodProto = method.getProto();
    auto interface = schema.asInterface();
    auto proto = method.getProto();
    auto line = kj::strTree(
        MODULE "Method(id=", method.getIndex(),
        ", name=\"", proto.getName(), "\"");
    // Params
    // output_struct_fields_ = false;
    TRAVERSE(param_list, interface, kj::str("parameters"), method.getParamType());
    std::vector<kj::String> fields;
    for (auto &field : fields_) {
      if (needed_names_defined(decls_.back(), field.needed_names)) {
        fields.emplace_back(kj::str(field.params));
      } else {
        // TODO: add to orphans
      }
    }
    line = kj::strTree(kj::mv(line), ", input_params=[", kj::strArray(fields, ", "), "]");

    // Results
    fields_.clear();
    fields.clear();
    TRAVERSE(param_list, interface, kj::str("results"), method.getResultType());
    for (auto &field : fields_) {
      if (needed_names_defined(decls_.back(), field.needed_names)) {
        fields.emplace_back(kj::str(field.params));
      } else {
        // TODO: add to orphans
      }
    }
    line = kj::strTree(kj::mv(line), ", output_params=[", kj::strArray(fields, ", "), "]");
    //line = kj::strTree(kj::mv(line), kj::strArray(param_list_, ", "), "]");
    //output_struct_fields_ = true;

    // Annotations
    TRAVERSE(annotations, schema, methodProto.getAnnotations());
    line = kj::strTree(kj::mv(line), get_stored_annotations(), ")");
    // TODO: fix needed names to put params and annotations on only if they're already valid.
    methods_.emplace_back(MethodInfo {line.flatten().cStr(), needed_names_});
    // define_name(kj::str(proto.getName()), line.flatten());
    return false;
  }

  bool post_visit_annotation(schema::Annotation::Reader, Schema schema) {
    needed_names_.emplace(schema.getShortDisplayName().cStr());
    annotations_.add(
        kj::str(check_keyword(schema.getShortDisplayName()), "(", last_value_, ")"));
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
        cog.outl('  last_type_ = kj::str(MODULE "%s");' % type.title())
        cog.outl('  break;')
      ]]]*/
      case schema::Type::VOID:
        last_type_ = kj::str(MODULE "Void");
        break;
      case schema::Type::BOOL:
        last_type_ = kj::str(MODULE "Bool");
        break;
      case schema::Type::TEXT:
        last_type_ = kj::str(MODULE "Text");
        break;
      case schema::Type::DATA:
        last_type_ = kj::str(MODULE "Data");
        break;
      case schema::Type::FLOAT32:
        last_type_ = kj::str(MODULE "Float32");
        break;
      case schema::Type::FLOAT64:
        last_type_ = kj::str(MODULE "Float64");
        break;
      case schema::Type::INT8:
        last_type_ = kj::str(MODULE "Int8");
        break;
      case schema::Type::INT16:
        last_type_ = kj::str(MODULE "Int16");
        break;
      case schema::Type::INT32:
        last_type_ = kj::str(MODULE "Int32");
        break;
      case schema::Type::INT64:
        last_type_ = kj::str(MODULE "Int64");
        break;
      case schema::Type::UINT8:
        last_type_ = kj::str(MODULE "Uint8");
        break;
      case schema::Type::UINT16:
        last_type_ = kj::str(MODULE "Uint16");
        break;
      case schema::Type::UINT32:
        last_type_ = kj::str(MODULE "Uint32");
        break;
      case schema::Type::UINT64:
        last_type_ = kj::str(MODULE "Uint64");
        break;
      //[[[end]]]
      case schema::Type::LIST:
        TRAVERSE(type, schema, type.getList().getElementType());
        last_type_ = kj::str("List(", last_type_, ")");
        break;
      case schema::Type::ENUM: {
        auto enumSchema = schemaLoader.get(
            type.getEnum().getTypeId(), type.getEnum().getBrand(), schema);
        needed_names_.emplace(enumSchema.getShortDisplayName().cStr());
        // TODO: Deal with generics here and the below types.
        last_type_ = kj::str(enumSchema.getShortDisplayName());
        break;
      }
      case schema::Type::INTERFACE: {
        auto ifaceSchema = schemaLoader.get(
            type.getInterface().getTypeId(), type.getInterface().getBrand(), schema);
        needed_names_.emplace(ifaceSchema.getShortDisplayName().cStr());
        last_type_ = kj::str(ifaceSchema.getShortDisplayName());
        break;
      }
      case schema::Type::STRUCT: {
        auto structSchema = schemaLoader.get(
            type.getStruct().getTypeId(), type.getStruct().getBrand(), schema);
        needed_names_.emplace(structSchema.getShortDisplayName().cStr());
        last_type_ = kj::str(structSchema.getShortDisplayName());
        break;
      }
      case schema::Type::ANY_POINTER:
        last_type_ = kj::str("AnyPointer");
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
        cog.outl('  last_value_ = kj::str(value.as<%s>());' % (ctype))
        cog.outl('  break;')
      ]]]*/
      case schema::Type::BOOL:
        last_value_ = kj::str(value.as<bool>());
        break;
      case schema::Type::INT64:
        last_value_ = kj::str(value.as<int64_t>());
        break;
      case schema::Type::UINT64:
        last_value_ = kj::str(value.as<uint64_t>());
        break;
      case schema::Type::FLOAT32:
        last_value_ = kj::str(value.as<float>());
        break;
      case schema::Type::FLOAT64:
        last_value_ = kj::str(value.as<double>());
        break;
      case schema::Type::INT8:
        last_value_ = kj::str(value.as<int8_t>());
        break;
      case schema::Type::INT16:
        last_value_ = kj::str(value.as<int16_t>());
        break;
      case schema::Type::INT32:
        last_value_ = kj::str(value.as<int32_t>());
        break;
      case schema::Type::UINT8:
        last_value_ = kj::str(value.as<uint8_t>());
        break;
      case schema::Type::UINT16:
        last_value_ = kj::str(value.as<uint16_t>());
        break;
      case schema::Type::UINT32:
        last_value_ = kj::str(value.as<uint32_t>());
        break;
      //[[[end]]]
      case schema::Type::VOID:
        last_value_ = kj::str("value");
        break;
      case schema::Type::TEXT:
        last_value_ = kj::str("'", value.as<Text>(), "'");
        break;
      case schema::Type::DATA:
        last_value_ = kj::str("b'", value.as<Data>(), "'");
        break;
      case schema::Type::LIST: {
        kj::Vector<kj::String> values;
        auto listType = type.asList();
        auto listValue = value.as<DynamicList>();
        for (auto element : listValue) {
          visit_value_dynamic(schema, listType.getElementType(), element);
          values.add(kj::mv(last_value_));
        }
        last_value_ = kj::str("[", kj::strArray(values, ", "), "]");
        break;
      }
      case schema::Type::ENUM: {
        auto enumValue = value.as<DynamicEnum>();
        last_value_ = kj::str(enumValue.getSchema().getShortDisplayName());
        needed_names_.emplace(last_value_.cStr());
        KJ_IF_MAYBE(enumerant, enumValue.getEnumerant()) {
          last_value_ = kj::str(
              kj::mv(last_value_), ".",
              check_keyword(enumerant->getProto().getName()));
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
            items.add(kj::str("\"", field.getProto().getName(), "\": ", last_value_));
          }
        }
        last_value_ = kj::str("{", kj::strArray(items, ", "), "}");
        break;
      }
      case schema::Type::INTERFACE: {
        last_value_ = kj::str(
            "interface? but that's not possible... how do you serialize an "
            "interface in a capnp file?");
        break;
      }
      case schema::Type::ANY_POINTER:
        last_value_ = kj::str(
            "any pointer? how do you serialize an anypointer in a capnp file");
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
        cog.outl('  last_value_ = kj::str(value.get%s());' % type.title())
        cog.outl('  break;')
      ]]]*/
      case schema::Type::BOOL:
        last_value_ = kj::str(value.getBool());
        break;
      case schema::Type::FLOAT32:
        last_value_ = kj::str(value.getFloat32());
        break;
      case schema::Type::FLOAT64:
        last_value_ = kj::str(value.getFloat64());
        break;
      case schema::Type::INT16:
        last_value_ = kj::str(value.getInt16());
        break;
      case schema::Type::INT32:
        last_value_ = kj::str(value.getInt32());
        break;
      case schema::Type::INT64:
        last_value_ = kj::str(value.getInt64());
        break;
      case schema::Type::INT8:
        last_value_ = kj::str(value.getInt8());
        break;
      case schema::Type::UINT16:
        last_value_ = kj::str(value.getUint16());
        break;
      case schema::Type::UINT32:
        last_value_ = kj::str(value.getUint32());
        break;
      case schema::Type::UINT64:
        last_value_ = kj::str(value.getUint64());
        break;
      case schema::Type::UINT8:
        last_value_ = kj::str(value.getUint8());
        break;
      //[[[end]]]
      case schema::Type::VOID:
        last_value_ = kj::str("void");
        break;
      case schema::Type::TEXT:
        last_value_ = kj::str("'", value.getText(), "'");
        break;
      case schema::Type::DATA:
        last_value_ = kj::str("b'", value.getData(), "'");
        break;
      case schema::Type::LIST: {
        kj::Vector<kj::String> values;
        auto listType = type.asList();
        auto listValue = value.getList().getAs<DynamicList>(listType);
        for (auto element : listValue) {
          visit_value_dynamic(schema, listType.getElementType(), element);
          values.add(kj::mv(last_value_));
        }
        last_value_ = kj::str("[", kj::strArray(values, ", "), "]");
        break;
      }
      case schema::Type::ENUM: {
        auto enumerants = type.asEnum().getEnumerants();
        last_value_ = kj::str(type.asEnum().getShortDisplayName());
        for (auto enumerant : enumerants) {
          if (enumerant.getIndex() == value.getEnum()) {
            last_value_ = kj::str(
                kj::mv(last_value_), ".", enumerant.getProto().getName());
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
            items.add(kj::str("\"", field.getProto().getName(), "\": ", last_value_));
          }
        }
        last_value_ = kj::str("{", kj::strArray(items, ", "), "}");
        break;
      }
      case schema::Type::INTERFACE: {
        last_value_ = kj::str(
            "interface? but that's not possible... how do you serialize an "
            "interface in a capnp file?");
        break;
      }
      case schema::Type::ANY_POINTER: {
        last_value_ = kj::str(
            "any pointer? how do you serialize an anypointer in a capnp file");
        break;
      }
    }
  }

};

constexpr const char CapnpcPython::FILE_SUFFIX[];

KJ_MAIN(CapnpcGenericMain<CapnpcPython>);
