# Build rimsort_steam native library
# Requires STEAMWORKS_SDK_PATH to be set to the extracted SDK root

SDK_PATH ?= $(STEAMWORKS_SDK_PATH)
HEADERS = $(SDK_PATH)/public/steam
UNAME := $(shell uname)

ifeq ($(UNAME), Darwin)
REDIST = $(SDK_PATH)/redistributable_bin/osx
OUTPUT = rimsort_steam.dylib
CXXFLAGS = -std=c++11 -shared -fPIC -fvisibility=hidden -install_name @rpath/$(OUTPUT) -Wl,-rpath,@loader_path
CXX = clang++
else
REDIST = $(SDK_PATH)/redistributable_bin/linux64
OUTPUT = rimsort_steam.so
CXXFLAGS = -std=c++11 -shared -fPIC -fvisibility=hidden
CXX = g++
endif

.PHONY: all clean

all: $(OUTPUT)

$(OUTPUT): rimsort_steam.cpp
	$(CXX) $(CXXFLAGS) -I$(HEADERS) -L$(REDIST) -lsteam_api -o $@ $<

clean:
	rm -f rimsort_steam.dylib rimsort_steam.so
