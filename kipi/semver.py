class Version:
    def __init__(self, s=None):
        self.major = 0
        self.minor = 0
        self.patch = 0
        self.pre_release = None
        if s:
            items = s.split(".")
            self.major = items[0]
            if len(items)>1:
                self.minor = items[1]
                if len(items)>2:
                    self.patch = items[2]
                    if "-" in self.patch:
                        self.pre_release = self.patch.split("-")[1]
                        self.patch = self.patch.split("-")[0]

    # return True of self > other
    def compare (self, other):
        if self.major > other.major:
            return True
        elif self.major == other.major:
            if self.minor > other.minor:
                return True
            elif self.minor == other.minor:
                if self.patch > other.patch:
                    return True
                elif self.patch == other.patch:
                    if (self.pre_release is None and not other.pre_release is None) or self.pre_release > other.pre_release:
                        return True
        return False

    def __str__ (self):
        return "%s %s %s %s" % (self.major, self.minor, self.patch, self.pre_release)
    __repr__= __str__


def is_later_version (a, b):
    ver_a = Version(a)
    return ver_a.compare (Version(b))

