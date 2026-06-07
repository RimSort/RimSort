# Build rimsort_steam native library
# Requires STEAMWORKS_SDK_PATH to be set to the extracted SDK root

SDK_PATH ?= $(STEAMWORKS_SDK_PATH)
OUTPUT_DIR ?= .
HEADERS = $(SDK_PATH)/public
UNAME := $(shell uname)

ifeq ($(UNAME), Darwin)
REDIST = $(SDK_PATH)/redistributable_bin/osx
LIB_NAME = rimsort_steam.dylib
CXXFLAGS = -std=c++11 -shared -fPIC -fvisibility=hidden -install_name @rpath/$(LIB_NAME) -Wl,-rpath,@loader_path
CXX = clang++
else
REDIST = $(SDK_PATH)/redistributable_bin/linux64
LIB_NAME = rimsort_steam.so
CXXFLAGS = -std=c++11 -shared -fPIC -fvisibility=hidden
CXX = g++
endif

OUTPUT = $(OUTPUT_DIR)/$(LIB_NAME)

.PHONY: all clean

all: $(OUTPUT)

$(OUTPUT): rimsort_steam.cpp
	$(CXX) $(CXXFLAGS) -I$(HEADERS) -L$(REDIST) -lsteam_api -o $@ $<

clean:
	rm -f $(OUTPUT_DIR)/rimsort_steam.dylib $(OUTPUT_DIR)/rimsort_steam.so
