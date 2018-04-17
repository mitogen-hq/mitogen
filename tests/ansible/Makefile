
all: \
	lib/modules/custom_binary_producing_junk \
	lib/modules/custom_binary_producing_json

lib/modules/custom_binary_producing_junk: lib/modules/src/custom_binary_producing_junk.c
	$(CC) -o $@ $<

lib/modules/custom_binary_producing_json: lib/modules/src/custom_binary_producing_json.c
	$(CC) -o $@ $<
