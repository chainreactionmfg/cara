@0xcb23fae3b2f57331;
# Similar to what is in the docs/advanced_usage.md
struct Root {
  field @0 :SubType1;
  struct SubType1 {
    subField @0 :Host;
    recurse @1 :Root;
  }
  struct Host {
    hostname @0 :Text;
    port @1 :Int16;
  }
}
