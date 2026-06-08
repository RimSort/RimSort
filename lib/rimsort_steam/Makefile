# Build rimsort_steam native library
# Requires STEAMWORKS_SDK_PATH to be set to the extracted SDK root

SDK_PATH ?= $(STEAMWORKS_SDK_PATH)
OUTPUT_DIR ?= .
HEADERS = $(SDK_PATH)/public
UNAME := $(shell uname)

ifeq ($(UNAME), Darwin)
REDIST = $(SDK_PATH)/redistributable_bin/osx
LIB_NAME = rimsort_steam.dylib
BASE_FLAGS = -std=c++11 -shared -fPIC -fvisibility=hidden -install_name @rpath/$(LIB_NAME) -Wl,-rpath,@loader_path
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

ifeq ($(UNAME), Darwin)
# macOS: build universal binary (arm64 + x86_64) via lipo
$(OUTPUT): rimsort_steam.cpp
	$(CXX) $(BASE_FLAGS) -arch arm64 -I$(HEADERS) -L$(REDIST) -lsteam_api -o $(OUTPUT).arm64 $<
	$(CXX) $(BASE_FLAGS) -arch x86_64 -I$(HEADERS) -L$(REDIST) -lsteam_api -o $(OUTPUT).x86_64 $<
	lipo -create $(OUTPUT).arm64 $(OUTPUT).x86_64 -output $@
	rm -f $(OUTPUT).arm64 $(OUTPUT).x86_64
else
$(OUTPUT): rimsort_steam.cpp
	$(CXX) $(CXXFLAGS) -I$(HEADERS) -L$(REDIST) -lsteam_api -o $@ $<
endif

clean:
	rm -f $(OUTPUT_DIR)/rimsort_steam.dylib $(OUTPUT_DIR)/rimsort_steam.so
	rm -f $(OUTPUT_DIR)/rimsort_steam.dylib.arm64 $(OUTPUT_DIR)/rimsort_steam.dylib.x86_64
