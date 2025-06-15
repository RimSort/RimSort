import re
from typing import List, Optional


class LogTreeNode:
    def __init__(
        self,
        label: str,
        duration: float = 0.0,
        percent: Optional[float] = None,
        self_time: Optional[float] = None,
        mod: Optional[str] = None,
    ):
        self.label = label
        self.duration = duration
        self.percent = percent
        self.self_time = self_time
        self.mod = mod
        self.children: List["LogTreeNode"] = []
        self.parent: Optional["LogTreeNode"] = None

    def add_child(self, child: "LogTreeNode") -> None:
        child.parent = self
        self.children.append(child)

    def __repr__(self) -> str:
        return f"<LogTreeNode {self.label} {self.duration}ms {self.percent}% mod={self.mod} children={len(self.children)}>"


def parse_rimworld_timing_log(lines: List[str]) -> Optional[LogTreeNode]:
    stack: List[LogTreeNode] = []
    root: Optional[LogTreeNode] = None
    timing_re = re.compile(
        r"^(?P<indent>(?: -)+)?\s*(?P<duration>[\d.]+)ms(?: \((?P<percent>[\d.]+)%\))? \(self: (?P<self>[\d.]+) ms\)(?: (?P<count>\d+x))? (?P<label>.+?)(?: for mod (?P<mod>\S+))?$"
    )
    for line in lines:
        m = timing_re.match(line)
        if m:
            indent = m.group("indent") or ""
            depth = indent.count("-")
            duration = float(m.group("duration"))
            percent = float(m.group("percent")) if m.group("percent") else None
            self_time = float(m.group("self")) if m.group("self") else None
            label = m.group("label").strip()
            mod = m.group("mod")
            node = LogTreeNode(label, duration, percent, self_time, mod)
            if depth == 0:
                root = node
                stack = [node]
            else:
                while len(stack) > depth:
                    stack.pop()
                stack[-1].add_child(node)
                stack.append(node)
    return root
