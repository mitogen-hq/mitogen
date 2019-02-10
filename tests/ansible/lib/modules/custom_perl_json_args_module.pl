#!/usr/bin/perl

my $json_args = <<'END_MESSAGE';
<<INCLUDE_ANSIBLE_MODULE_JSON_ARGS>>
END_MESSAGE

print '{';
print '   "message": "I am a perl script! Here is my input.",' . "\n";
print '   "input": ' . $json_args;
print '}' . "\n";
