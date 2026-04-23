#! /bin/python3
import random
import re
import copy

# =========================
# AST BASE
# =========================

class Node:
    def generate(self, grammar):
        raise NotImplementedError

    def clone(self):
        return copy.deepcopy(self)

    def mutate(self, grammar):
        return self


# =========================
# NODE TYPES
# =========================

class Literal(Node):
    def __init__(self, value):
        self.value = value

    def generate(self, grammar):
        return self.value

    def mutate(self, grammar):
        # small chance to corrupt literal
        if random.random() < 0.2 and len(self.value) > 0:
            idx = random.randint(0, len(self.value)-1)
            c = chr(random.randint(32, 126))
            self.value = self.value[:idx] + c + self.value[idx+1:]
        return self


class CharClass(Node):
    def __init__(self, chars):
        self.chars = chars

    def generate(self, grammar):
        return random.choice(self.chars)

    def mutate(self, grammar):
        # expand charset randomly
        if random.random() < 0.2:
            self.chars.append(chr(random.randint(32, 126)))
        return self


class Sequence(Node):
    def __init__(self, nodes):
        self.nodes = nodes

    def generate(self, grammar):
        return ''.join(n.generate(grammar) for n in self.nodes)

    def mutate(self, grammar):
        if not self.nodes:
            return self

        choice = random.choice(["swap", "delete", "mutate_child"])

        if choice == "swap" and len(self.nodes) > 1:
            i, j = random.sample(range(len(self.nodes)), 2)
            self.nodes[i], self.nodes[j] = self.nodes[j], self.nodes[i]

        elif choice == "delete" and len(self.nodes) > 1:
            self.nodes.pop(random.randrange(len(self.nodes)))

        elif choice == "mutate_child":
            random.choice(self.nodes).mutate(grammar)

        return self
    
class NumberRange(Node):
    def __init__(self, min_val, max_val, is_int=True):
        self.min_val = min_val
        self.max_val = max_val
        self.is_int = is_int

    def generate(self, grammar):
        if self.is_int:
            return str(random.randint(int(self.min_val), int(self.max_val)))
        else:
            return str(random.uniform(self.min_val, self.max_val))

class Alternation(Node):
    def __init__(self, options):
        self.options = options

    def generate(self, grammar):
        return random.choice(self.options).generate(grammar)

    def mutate(self, grammar):
        # bias towards picking unusual branch
        random.choice(self.options).mutate(grammar)
        return self


class Repeat(Node):
    def __init__(self, node, min_r, max_r):
        self.node = node
        self.min_r = min_r
        self.max_r = max_r

    def generate(self, grammar):
        count = random.randint(self.min_r, self.max_r)
        return ''.join(self.node.generate(grammar) for _ in range(count))

    def mutate(self, grammar):
        # widen or shrink repetition bounds
        if random.random() < 0.3:
            self.max_r += random.randint(1, 3)
        if random.random() < 0.3 and self.min_r > 0:
            self.min_r -= 1
        return self


class Ref(Node):
    def __init__(self, name):
        self.name = name

    def generate(self, grammar):
        return grammar[self.name].generate(grammar)

    def mutate(self, grammar):
        grammar[self.name].mutate(grammar)
        return self


# =========================
# PARSER (same DSL)
# =========================

def parse_char_class(s):
    chars = []
    i = 0
    while i < len(s):
        if i+2 < len(s) and s[i+1] == '-':
            chars.extend(chr(c) for c in range(ord(s[i]), ord(s[i+2])+1))
            i += 3
        else:
            chars.append(s[i])
            i += 1
    return CharClass(chars)


def tokenize(expr):
    token_spec = [
        ("STRING", r'"(?:\\.|[^"\\])*"'),
        ("CLASS", r'\[[^\]]+\]'),
        ("REPEAT", r'\{\d+(,\d+)?\}'),
        ("REF", r'<[A-Za-z_][A-Za-z0-9_]*>'),  # FIXED
        ("ALT", r'\|'),
        ("LPAREN", r'\('),
        ("RPAREN", r'\)'),
        ("SKIP", r'\s+'),
        ("NUMRANGE", r'<number_range\s+min=[^ >]+\s+max=[^>]+>')
    ]

    tok_regex = '|'.join(f'(?P<{n}>{p})' for n, p in token_spec)

    tokens = []
    pos = 0

    for m in re.finditer(tok_regex, expr):
        if m.start() != pos:
            raise ValueError(f"Tokenizer skipped input at: {expr[pos:m.start()]}")
        if m.lastgroup != "SKIP":
            tokens.append((m.lastgroup, m.group()))
        pos = m.end()

    if pos != len(expr):
        raise ValueError(f"Tokenizer stopped early at: {expr[pos:]}")

    return tokens


def parse(expr):
    tokens = tokenize(expr)
    pos = 0

    print("PARSING:", expr)
    print("TOKENS:", tokens)

    def parse_expr():
        nonlocal pos

        nodes = [parse_sequence()]

        while pos < len(tokens) and tokens[pos][0] == "ALT":
            pos += 1
            nodes.append(parse_sequence())

        return nodes[0] if len(nodes) == 1 else Alternation(nodes)

    def parse_sequence():
        nonlocal pos

        seq = []
        while pos < len(tokens) and tokens[pos][0] not in ("RPAREN", "ALT"):
            seq.append(parse_term())

        return Sequence(seq) if len(seq) > 1 else seq[0]

    def parse_term():
        nonlocal pos

        tok = tokens[pos]
        pos += 1

        if tok[0] == "STRING":
            node = Literal(tok[1][1:-1])

        elif tok[0] == "CLASS":
            node = parse_char_class(tok[1][1:-1])

        elif tok[0] == "REF":
            node = Ref(tok[1][1:-1])
        elif tok[0] == "NUMRANGE":
            m = re.match(r'<number_range\s+min=([^\s]+)\s+max=([^\s]+)>', tok[1])
            min_val = float('-inf') if m.group(1) == '-inf' else float(m.group(1))
            max_val = float('inf') if m.group(2) == 'inf' else float(m.group(2))
            node = NumberRange(min_val, max_val)

        elif tok[0] == "LPAREN":
            node = parse_expr()

            if pos >= len(tokens) or tokens[pos][0] != "RPAREN":
                print("DEBUG TOKENS:", tokens)
                print("DEBUG POS:", pos)
                raise ValueError("Missing closing parenthesis")

            pos += 1

        else:
            raise ValueError(tok)

        # handle repetition
        if pos < len(tokens) and tokens[pos][0] == "REPEAT":
            rep = tokens[pos][1][1:-1].split(",")
            pos += 1

            if len(rep) == 1:
                node = Repeat(node, int(rep[0]), int(rep[0]))
            else:
                node = Repeat(node, int(rep[0]), int(rep[1]))

        return node

    return parse_expr()


# =========================
# GRAMMAR
# =========================

class Grammar:
    def __init__(self):
        self.rules = {}

    def add(self, name, expr):
        self.rules[name] = parse(expr)

    def generate(self, start):
        return self.rules[start].generate(self.rules)

    def mutate(self):
        random.choice(list(self.rules.values())).mutate(self.rules)


# =========================
# BUILD GRAMMAR
# =========================

def build():
    g = Grammar()

    # -------------------------
    # Basic symbols
    # -------------------------
    g.add("dot", '"."')
    g.add("slash", '"/"')
    g.add("digit", '[0-9]')
    g.add("letter", '[a-zA-Z]')
    g.add("quote", '["]')  # simpler, no escapes needed

    # -------------------------
    # IPv4
    # -------------------------
    g.add("octet", '("25"[0-5] | "2"[0-4]<digit> | "1"<digit><digit> | <digit>{1,2})')
    g.add("ipv4", '<octet> <dot> <octet> <dot> <octet> <dot> <octet>')
    g.add("cidr4", '<number_range min=0 max=32>')
    g.add("ipv4_cidr", '<ipv4> <slash> <cidr4>')

    # -------------------------
    # IPv6
    # -------------------------
    g.add("hex", '[0-9a-f]{1,4}')
    g.add("ipv6", '<hex> ":" <hex> ":" <hex> ":" <hex> ":" <hex> ":" <hex> ":" <hex> ":" <hex>')
    g.add("cidr6", '<number_range min=0 max=128>')
    g.add("ipv6_cidr", '<ipv6> "/" <cidr6>')

    # -------------------------
    # JSON-like
    # -------------------------
    g.add("string", '<quote> (<letter>|<digit>){1,6} <quote>')
    g.add("number", '<digit>{1,3}')
    g.add("value", '<string> | <number> |<object>')
    g.add("pair", '<string> ":" <value>')
    g.add("object", '"{" <pair> ("," <pair>){0,3} "}"')

    return g


# =========================
# DRIVER
# =========================

def run(n=10, mutations_per_sample=3):
    import copy

    base = build()

    print("\n==============================")
    print(" TREE-AWARE GRAMMAR FUZZER ")
    print("==============================\n")

    # ---------- JSON ----------
    print("\n====== JSON ======\n")
    for i in range(n):
        g_valid = copy.deepcopy(base)
        valid = g_valid.generate("object")

        print(f"[{i:02}] VALID   : {valid}")

        for m in range(mutations_per_sample):
            g_mut = copy.deepcopy(base)

            # apply multiple structural mutations
            for _ in range(random.randint(1, 5)):
                g_mut.mutate()

            mutated = g_mut.generate("object")
            print(f"     MUT[{m}] : {mutated}")

        print()
    
    # ---------- IPv4 ----------
    print("\n====== IPv4 CIDR ======\n")
    for i in range(n):
        g_valid = copy.deepcopy(base)
        valid = g_valid.generate("ipv4_cidr")

        print(f"[{i:02}] VALID   : {valid}")

        for m in range(mutations_per_sample):
            g_mut = copy.deepcopy(base)

            for _ in range(random.randint(1, 5)):
                g_mut.mutate()

            mutated = g_mut.generate("ipv4_cidr")
            print(f"     MUT[{m}] : {mutated}")

        print()

    # ---------- IPv6 ----------
    print("\n====== IPv6 CIDR ======\n")
    for i in range(n):
        g_valid = copy.deepcopy(base)
        valid = g_valid.generate("ipv6_cidr")

        print(f"[{i:02}] VALID   : {valid}")

        for m in range(mutations_per_sample):
            g_mut = copy.deepcopy(base)

            for _ in range(random.randint(1, 5)):
                g_mut.mutate()

            mutated = g_mut.generate("ipv6_cidr")
            print(f"     MUT[{m}] : {mutated}")

        print()
    
if __name__ == "__main__":
    run(10)