@0x8be65cad6be49bcb;

interface FooIface {
    callback @0 (foo :FooIface) -> ();
}

interface BarIface {
    returnCb @0 () -> (cb :BazIface);
}

interface BazIface {
    call @0 (is_called :Bool) -> ();
}


interface ThreeIface {
    interface Simple {
        normalMethod @0 (input :Text) -> (output :Text);
    }
    returnIface @0 () -> (return :Simple);
    acceptIface @1 (accept :Simple) -> ();
}
