from __future__ import print_function
import os.path
import subprocess as sub
import re
from distutils.version import LooseVersion
from collections import OrderedDict
from operator import attrgetter
import time

import sublime
import sublime_plugin

try:
    from SublimeMessages import message_manager
    from SublimeMessages import multiconf
except ImportError:
    from Messages import message_manager
    from Messages import multiconf

MIN_PYLINT_VERSION = LooseVersion("1.1.0")

def plugin_loaded():
    global pylint_msg_src, _tmp_messages  # pylint: disable=W
    pylint_msg_src = PylintMessageSource()
    try:
        pylint_msg_src.messages = _tmp_messages  # pylint: disable=W0201
    except NameError:
        pass
    message_manager.message_manager.add_source(pylint_msg_src,
                                           pylint_msg_src.priority)

def plugin_unloaded():
    try:
        global pylint_msg_src, _tmp_messages  # pylint disable=W
        _tmp_messages = pylint_msg_src.messages
        message_manager.message_manager.del_source(pylint_msg_src)
        del pylint_msg_src
    except NameError:
        pass

def get_pylint_bin(settings_obj):
    """ returns a valid, runnable path to pylint, and its LooseVersion """
    # settings_obj = sublime.load_settings("Pylint.sublime-settings")
    ver = None
    pylint_bin = multiconf.get(settings_obj, "pylint_bin", None)

    # umm, why is this /usr/bin/python, yet the autodiscover below works??
    # print("!!", sub.check_output(["python", "--version"], stderr=sub.STDOUT))

    # test that the pylint_bin path is good and check its version
    if pylint_bin is not None:
        try:
            ver = sub.check_output([pylint_bin, "--version"]).decode()
            ver = LooseVersion(re.search(r"([0-9]+\.?)+", ver).group())
            if ver < MIN_PYLINT_VERSION:
                print("Pylint: pylint_bin version <", MIN_PYLINT_VERSION,
                      ", trying autodiscover [", pylint_bin, "]")
                pylint_bin = None
        except (OSError, sub.CalledProcessError):
            print("Pylint: pylint_bin not found, trying autodiscover [",
                  pylint_bin, "]")
            pylint_bin = None

    # of no pylint_bin or it's not a good version, try autodiscovering
    if pylint_bin is None:
        cmd = "from __future__ import print_function;" \
              "import pylint; " \
              "print(pylint.__path__[0])"
        try:
            python_bin = multiconf.get(settings_obj, "python_bin", "python")
            print("Pylint: using python [", python_bin, "]")
            module_path = sub.check_output([python_bin, "-c", cmd]).decode()
            pylint_bin = os.path.normpath(os.path.join(
                module_path, '..', '..', '..', '..', 'bin', 'pylint'))
            # check the version on the autodiscovered pylint
            ver = sub.check_output([pylint_bin, "--version"]).decode()
            ver = LooseVersion(re.search(r"([0-9]+\.?)+", ver).group())
            if ver < MIN_PYLINT_VERSION:
                print("Pylint: autodiscover failed; version <",
                      MIN_PYLINT_VERSION, "[", pylint_bin, "]")
                pylint_bin = None
        except (OSError, sub.CalledProcessError) as e:
            print("Pylint: autodiscover failed;", str(e))
            if python_bin is not None:
                which_python = sub.check_output(["which", python_bin]).decode()
                print("Pylint: maybe pylint isn't installed for ",
                      which_python.strip())

    if pylint_bin is None:
        print("Pylint: Could not find pylint :(")
        return None, None
    print("Pylint: using executable at [", pylint_bin, "]")
    return pylint_bin, ver

def lintable_view(view):
    return view.file_name().endswith('.py') or \
           "python" in view.settings().get('syntax').lower()


class PylintMessageSource(message_manager.LineMessageSource):
    prefix = "Pylint"

    _pylint_bin = None
    _pylint_ver = None  # pylint version number, filled when checking binary
    _output_re = None

    _active_lint = None

    def __init__(self):
        super(PylintMessageSource, self).__init__()
        self._active_lint = {}

    def settings_callback(self):
        super(PylintMessageSource, self).settings_callback()
        # update pylint_bin on the callback to make sure paths are valid
        self._pylint_bin = None
        _ = self.pylint_bin

    @property
    def markers(self):
        pth = self.get_icon_path()
        epth = pth + "/error.png"
        wpth = pth + "/warning.png"
        ipth = pth + "/info.png"
        ret = OrderedDict([("I", (ipth, "SublimeMessages.info")),
                           ("R", (ipth, "SublimeMessages.info")),
                           ("C", (ipth, "SublimeMessages.info")),
                           ("W", (wpth, "SublimeMessages.warning")),
                           ("E", (epth, "SublimeMessages.error")),
                           ("F", (epth, "SublimeMessages.error"))
                          ])
        return ret

    @property
    def pylint_bin(self):
        if self._pylint_bin is None:
            self._pylint_bin, self._pylint_ver = get_pylint_bin(self.settings)
            self._output_re = re.compile(r"""
                ^(?P<file>.+?):(?P<line>[0-9]+):
                (?P<cat>[A-Za-z]):(?P<errid>[A-Za-z]\d+):
                (?P<symbol>[A-Za-z0-9\-]+):(?P<msg>.*)
                """, re.IGNORECASE | re.VERBOSE)
        return self._pylint_bin

    def run(self, view):
        if self.pylint_bin is None:
            print("No pylint >", MIN_PYLINT_VERSION,
                  "accessable, not linting")
            return None

        window = view.window()
        fname = view.file_name()
        file_info = message_manager.FileInfoDict()
        if not window.id() in self.messages:
            self.messages[window.id()] = {}
        # make a lookup for the order of severity
        # sev_lookup = OrderedDict(zip(self.markers.keys(), itertools.count()))

        cmd = [self.pylint_bin, "-r", "no",
               "--msg-template", "{path}:{line}:{C}:{msg_id}:{symbol}:{msg}"]
        disable_msgs = multiconf.get(self.settings, "disable", None)
        if disable_msgs is not None:
            disable_msgs = ",".join(disable_msgs)
            cmd += ["-d", disable_msgs]
        extra_args = multiconf.get(self.settings, "extra_args", [])
        cmd += extra_args
        cmd.append(fname)
        p = sub.Popen(cmd, stdout=sub.PIPE, stderr=sub.PIPE)
        raw_stdout, raw_stderr = p.communicate()

        # check stderr for a bad lint run
        err = raw_stderr.decode()
        err_lines = [line for line in err.splitlines()
                     if line and not line.startswith('Using config file')]
        if len(err_lines) > 0:
            print("*******************")
            print("Fatal pylint error:")
            print("------------------")
            print("{0}".format(err))
            print("*******************")
            sublime.error_message("Fatal pylint error, check console for "
                                  "details")
            return None

        ignore = multiconf.get(self.settings, "ignore", [])
        ignore = [t.lower() for t in ignore]
        out = raw_stdout.decode()
        for line in out.strip().splitlines():
            if line.startswith("*************"):
                continue

            # print(line)
            m = re.match(self._output_re, line)
            if m:
                d = m.groupdict()
                # print(d)
                line_num = int(d['line']) # - 1
                if d['errid'].lower() not in ignore and d['symbol'] not in ignore:
                    if not line_num in file_info:
                        file_info[line_num] = []
                    msg = "{0}: {1}".format(d["errid"], d["msg"].strip())
                    err_info = message_manager.ErrorInfo(self, line_num,
                                                         d["cat"], msg,
                                                         extra=True,
                                                         errid=d['errid'],
                                                         symbol=d['symbol'])
                    file_info[line_num].append(err_info)
                    file_info[line_num].sort(key=attrgetter("order"),
                                             reverse=True)

        # self.messages[window.id()] = window_container
        self.messages[window.id()][fname] = file_info
        self.mark_errors(window, view)

    def kickoff(self, view):
        vid = view.id()
        try:
            if self._active_lint[vid] is not None:
                while self._active_lint is not None:
                    time.sleep(0.2)
        except KeyError:
            # make sure vid is in the active lint dict, this will
            # be the first linting
            self._active_lint[vid] = None

        kickoff_time = time.time()
        self._active_lint[vid] = kickoff_time
        # sublime.set_timeout_async(lambda: pylint_msg_src.run(view), 100)
        view.erase_status(self.status_key)
        sublime.set_timeout(lambda: self.progress_tracker(view, kickoff_time),
                            100)
        self.run(view)
        self._active_lint[view.id()] = None

    def progress_tracker(self, view, kickoff_time, i=0):
        if self._active_lint[view.id()] == kickoff_time:
            icons = [u"◐", u"◓", u"◑", u"◒"]
            view.set_status("active_pylint", "Pylinting: " + icons[i])
            i = (i + 1) % 4
            callback = lambda: self.progress_tracker(view, kickoff_time, i)
            sublime.set_timeout(callback, 200)
        else:
            view.erase_status("active_pylint")


class PylintSourceListener(sublime_plugin.EventListener):
    @staticmethod
    def on_post_save_async(view):
        if lintable_view(view):
            pylint_msg_src.kickoff(view)


class PylintIgnoreCommand(sublime_plugin.TextCommand):
    def run(self, edit, **kwargs):
        view = self.view
        fname = view.file_name()
        window = view.window()
        point = view.sel()[0].end()

        w_id = window.id()
        src = pylint_msg_src

        if w_id in src.messages and fname in src.messages[w_id]:
            err_reg = None
            for severity in src.markers.keys():
                regions = view.get_regions(src.marker_key + severity)  # pylint: disable=maybe-no-member
                for reg in regions:
                    if reg.contains(point):
                        err_reg = reg
                        break
                if err_reg is not None:
                    break
            if err_reg is not None:
                # FIXME: xpos shouldn't be a key so we can track > 1 error
                # per line for each source
                finfo = src.messages[w_id][fname]
                mlst = [i.symbol for i in finfo[int(err_reg.xpos)]]

                pylint_statement = "pylint: disable="
                line_region = view.line(point)
                line_txt = view.substr(line_region)
                if pylint_statement in line_txt:
                    # look for what's already there...
                    ending = line_txt.rstrip().split(pylint_statement)[-1]
                    already_disabled = ending.split(',')
                    for m in already_disabled:
                        try:
                            mlst.remove(m)
                        except ValueError:
                            pass
                    start_blurb = ","
                else:
                    start_blurb = "  # " + pylint_statement

                if len(mlst) == 0:
                    return None

                # add only unique items
                seen = set()
                seen_add = seen.add
                mlst = [m for m in mlst if m not in seen and not seen_add(m)]

                msg = ",".join(mlst)
                line_txt = line_txt.rstrip() + start_blurb + msg
                view.replace(edit, line_region, line_txt)


##
## EOF
##
