#!/usr/bin/perl

my $WANT_JSON = 1;

my $json;
{
  local $/; #Enable 'slurp' mode
  open my $fh, "<", $ARGV[0];
  $json_args = <$fh>;
  close $fh;
}

print "{\n";
print ' "message": "I am a want JSON perl script! Here is my input.",' . "\n";
print ' "input": ' . $json_args . "\n";
print "}\n";
