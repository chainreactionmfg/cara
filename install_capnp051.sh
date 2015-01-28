if [[ ! -e capnproto ]]; then
  git clone --depth=1 --single-branch -b release-0.5.1 https://github.com/kentonv/capnproto.git
  cd capnproto/c++
  if [[ ! -e capnp ]]; then
    autoreconf -i && ./configure && make -j5 && sudo make install
  fi
  cd ../../
fi

