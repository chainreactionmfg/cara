@0xdeadbeef00110001;

struct GenericStruct (T) {
  field @0 :GenericStruct(T);
  defaulted @1 :Text = "defaulteds";
  list @2 :List(GenericStruct(T));

  annotation ann (*) :T;

  struct Nested(U) {
    first @0 :GenericStruct(T).Nested(T);
    second @1 :GenericStruct(U);
  }
  struct Nongeneric {
    templated @0 :T;
    doubleTemplated @1 :GenericStruct(Text);
  }
}

interface GenericIface (T) {
  struct Nested (U) {
    field @0 :GenericStruct.Nested(T);
  }
  templated @0 [X] (in :T) -> (out :X);
  normal @1 (in :T) -> (out :T);
}

annotation enumAnnotation (enumerant) :Int32;
enum BasicEnum {
  first @0 $enumAnnotation(3);
  second @1;
}

const value :Int8 = 0 $GenericStruct(Text).ann("ann");
