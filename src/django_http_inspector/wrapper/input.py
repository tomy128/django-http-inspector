class CapturingInput:
    """Tee bytes read by a WSGI application without pre-consuming input."""

    def __init__(self, stream, limit, declared_size=None):
        self.stream = stream
        self.limit = limit
        self.declared_size = declared_size
        self.captured = bytearray()
        self.observed_size = 0
        self.read_error = False
        self.exhausted = declared_size == 0

    def _observe(self, data):
        if not data:
            self.exhausted = True
            return data
        self.observed_size += len(data)
        remaining = self.limit - len(self.captured)
        if remaining > 0:
            self.captured.extend(data[:remaining])
        if self.declared_size is not None and self.observed_size >= self.declared_size:
            self.exhausted = True
        return data

    def _call(self, name, *args):
        try:
            return self._observe(getattr(self.stream, name)(*args))
        except Exception:
            self.read_error = True
            raise

    def read(self, size=-1):
        return self._call("read", size)

    def readline(self, size=-1):
        return self._call("readline", size)

    def readlines(self, hint=-1):
        lines = []
        total = 0
        while hint < 0 or total < hint:
            line = self.readline()
            if not line:
                break
            lines.append(line)
            total += len(line)
        return lines

    def __iter__(self):
        return self

    def __next__(self):
        line = self.readline()
        if not line:
            raise StopIteration
        return line

    @property
    def truncated(self):
        return self.observed_size > self.limit

    @property
    def incomplete(self):
        if self.read_error:
            return True
        if self.declared_size is not None:
            return self.observed_size < self.declared_size
        return not self.exhausted
