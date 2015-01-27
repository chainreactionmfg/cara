# From pseud's .travis.yml:
# https://github.com/ezeep/pseud/blob/e8be2f309b3385c5ea0bfcacf1668e84cf25bf6f/.travis.yml#L11
if [[ ! -e zeromq4-1-master ]]; then
  sudo add-apt-repository -y ppa:shnatsel/dnscrypt
  sudo apt-get update && sudo apt-get install libsodium-dev
  curl https://github.com/zeromq/zeromq4-1/archive/master.zip -L > zeromq4-1-master.zip
  unzip zeromq4-1-master.zip
  cd zeromq4-1-master && ./autogen.sh && ./configure && make -j && sudo make install && sudo ldconfig && cd ..
fi

