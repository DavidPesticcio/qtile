import subprocess, os, time, sys, socket, traceback
import Xlib.display, Xlib.X
import libpry
import libqtile

class XNest(libpry.TestContainer):
    def __init__(self, xinerama, display=":1"):
        libpry.TestContainer.__init__(self)
        self.xinerama = xinerama
        if xinerama:
            self.name = "XNestXinerama"
        self["display"] = display

    def setUp(self):
        args = [ "Xnest", "-geometry", "800x600", self["display"], "-ac", "-sync"]
        if self.xinerama:
            args.extend(["+xinerama", "-scrns", "2"])
        self.sub = subprocess.Popen(
                        args,
                        stdout = subprocess.PIPE,
                        stderr = subprocess.PIPE,
                    )

    def tearDown(self):
        os.kill(self.sub.pid, 9)
        os.waitpid(self.sub.pid, 0)
                

class _QTileTruss(libpry.TmpDirMixin, libpry.AutoTree):
    def setUp(self):
        libpry.TmpDirMixin.setUp(self)
        # Try until XNest is up
        for i in range(20):
            try:
                d = Xlib.display.Display(self["display"])
                break
            except (Xlib.error.DisplayConnectionError, Xlib.error.ConnectionClosedError):
                time.sleep(0.1)
        else:
            raise AssertionError, "Could not connect to display."
        d.close()
        del d
        
        # Now start for real
        self["fname"] = os.path.join(self["tmpdir"], "qtilesocket")
        pid = os.fork()
        if pid == 0:
            # Run this in a sandbox...
            try:
                q = libqtile.QTile(self["display"], self["fname"])
                q.loop()
            except Exception, e:
                traceback.print_exc(file=sys.stderr)
            sys.exit(0)
        else:
            self.qtilepid = pid
            c = libqtile.ipc.Client(self["fname"])
            # Wait until qtile is up before continuing
            for i in range(20):
                try:
                    if c.call("status") == "OK":
                        break
                except socket.error:
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError, "Timeout waiting for Qtile"
        self.testwindows = []
        self.c = libqtile.ipc.Client(self["fname"])

    def tearDown(self):
        libpry.TmpDirMixin.tearDown(self)
        try:
            self._kill(self.qtilepid)
        except OSError:
            # The process may have died due to some other error
            pass
        for pid in self.testwindows[:]:
            self._kill(pid)
        self.testwindows = []

    def testWindow(self, name):
        c = libqtile.ipc.Client(self["fname"])
        start = c.call("clientcount")
        pid = os.fork()
        if pid == 0:
            os.execv("scripts/window", ["scripts/window", self["display"], name])
        for i in range(20):
            if c.call("clientcount") > start:
                break
            time.sleep(0.1)
        else:
            raise AssertionError("Window never appeared...")
        self.testwindows.append(pid)
        return pid

    def _kill(self, pid):
        os.kill(pid, 9)
        os.waitpid(pid, 0)
        if pid in self.testwindows:
            self.testwindows.remove(pid)

    def kill(self, pid):
        c = libqtile.ipc.Client(self["fname"])
        start = c.call("clientcount")
        self._kill(pid)
        for i in range(20):
            if c.call("clientcount") < start:
                break
            time.sleep(0.1)
        else:
            raise AssertionError("Window could not be killed...") 


class uQTile(_QTileTruss):
    def test_events(self):
        assert self.c.call("status") == "OK"

    def test_mapRequest(self):
        self.testWindow("one")
        info = self.c.call("groupinfo", "a")
        assert "one" in info["clients"]
        assert info["focus"] == "one"

        self.testWindow("two")
        info = self.c.call("groupinfo", "a")
        assert "two" in info["clients"]
        assert info["focus"] == "two"

    def test_unmap(self):
        one = self.testWindow("one")
        two = self.testWindow("two")
        info = self.c.call("groupinfo", "a")
        assert info["focus"] == "two"

        assert self.c.call("clientcount") == 2
        self.kill(two)

        assert self.c.call("clientcount") == 1
        info = self.c.call("groupinfo", "a")
        assert info["focus"] == "one"

        self.kill(one)
        assert self.c.call("clientcount") == 0
        info = self.c.call("groupinfo", "a")
        assert info["focus"] == None

    def test_focus(self):
        self.testWindow("one")
        self.testWindow("two")
        self.testWindow("three")

        info = self.c.call("groupinfo", "a")
        assert info["focus"] == "three"
        self.c.call("focusnext")
        info = self.c.call("groupinfo", "a")
        assert info["focus"] == "one"
        self.c.call("focusnext")
        info = self.c.call("groupinfo", "a")
        assert info["focus"] == "two"

        self.c.call("focusprevious")
        info = self.c.call("groupinfo", "a")
        assert info["focus"] == "one"

    def test_setgroup(self):
        self.testWindow("one")
        assert self.c.call("pullgroup", "nonexistent") == "No such group"
        self.c.call("pullgroup", "b")
        if self.c.call("screencount") == 1:
            assert self.c.call("groupinfo", "a")["screen"] == None
        else:
            assert self.c.call("groupinfo", "a")["screen"] == 1
        assert self.c.call("groupinfo", "b")["screen"] == 0
        self.c.call("pullgroup", "c")
        assert self.c.call("groupinfo", "c")["screen"] == 0


tests = [
    XNest(xinerama=True), [
        uQTile()
    ],
    XNest(xinerama=False), [
        uQTile()
    ]
]
