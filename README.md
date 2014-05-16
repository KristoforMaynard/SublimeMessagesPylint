SublimeMessagesPylint
=====================

Yet another plugin for pylint in Sublime Text. Unlike others, this one has a brittish accent. The main difference is this plugin works with the SublimeMessages plugin.

The prerequisits for this plugin are:
 - SublimeMessages plugin
 - pylint version >= 1.0.1

Much of the inspiriation for this plugin comes from the pylinter plugin, but with an effort to make it a bit more natural. For instance, when you edit a file, and marked lines move, the gutter marks and status messages move with them.

How it works:
-------------

Lints files on save.

`pylint disable` comments can be added to ignore all message types on a line with `ctrl`+`alt`+`i` (Linux) or `super`+`alt`+`i` (OS X).

Gutter mark colors are determined by the following scopes in your color scheme:
 - SublimeMessages.error
 - SublimeMessages.warning
 - SublimeMessages.info

Settings:
---------
 - `enabled` true or false
 - `pylint_bin` path to pylint executable
 - `python_bin` path to python interpreter that can import pylint (only used if pylint_bin is not found and auto-discover fails)
 - `disable` list of pylint messages to ignore (ex: ["I0011"])
