from collections import deque


def trace_impact(edges: list[tuple[str, str]], start: str, customer_facing: list[str]) -> list[dict]:
   
    graph: dict[str, set[str]] = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)  # set => cạnh trùng không ảnh hưởng

    prev: dict[str, str | None] = {start: None}  # đã thăm và điểm trước đó (chống vòng lặp)
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for nxt in sorted(graph.get(node, ())):
            if nxt not in prev:
                prev[nxt] = node
                queue.append(nxt)

    results = []
    for target in set(customer_facing):
        if target in prev:
            path, node = [], target
            while node is not None:
                path.append(node)
                node = prev[node]
            path.reverse()
            results.append({"service": target, "path": path, "edges": len(path) - 1})
    results.sort(key=lambda r: (r["edges"], r["service"]))
    return results
