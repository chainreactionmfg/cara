# Changelog

## 0.8.0

### Pseud Integration

* Added support for registering interfaces with superclasses and calling the
  right method on the other side.

### Enhancements

* A List of Structs can use a nested query with Get.
* The ID of declarations are now in the generated code and accessible.

### Bugs

* Enums don't have empty default values.
* Structs can do type coercion when doing equality checks. Struct() == {} can
  work.
* ReplaceTypes works on superclasses too.

## 0.7.0

### Enhancements

* Add support for groups and unions in the generated code and the helper library.

## 0.6.0

### Enhancements

* Make ReplaceTypes useful beyond just for Templates.

