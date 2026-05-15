import re
import shlex

class SearchQueryEvaluator:
    def __init__(self, query: str):
        self.raw_query = query
        self.ast = self._build_ast(query)

    def evaluate(self, text: str) -> bool:
        if not self.ast:
            return True
        return self._eval_node(self.ast, text.lower())

    def _eval_node(self, node, text: str) -> bool:
        if isinstance(node, str):
            return node in text

        op = node[0]
        if op == 'AND':
            return self._eval_node(node[1], text) and self._eval_node(node[2], text)
        elif op == 'OR':
            return self._eval_node(node[1], text) or self._eval_node(node[2], text)
        elif op == 'NOT':
            return not self._eval_node(node[1], text)
        return False

    def _tokenize(self, query: str):
        # We need a proper tokenizer
        # tokens: quoted strings, AND, OR, NOT, &&, ||, &, |, !, (, ), or literals

        token_pattern = re.compile(
            r'"[^"]+"'            # Double quoted strings
            r"|'[^']+'"           # Single quoted strings
            r"|\&\&|\|\|"         # Logical operators
            r"|[\(\)\!\|\&]"      # Punctuation
            r"|[^\s\(\)\!\|\&]+"  # Words
        )

        raw_tokens = token_pattern.findall(query)
        tokens = []
        for t in raw_tokens:
            t_upper = t.upper()
            if t_upper in ('AND', '&&', '&'):
                tokens.append('AND')
            elif t_upper in ('OR', '||', '|'):
                tokens.append('OR')
            elif t_upper in ('NOT', '!'):
                tokens.append('NOT')
            elif t == '(' or t == ')':
                tokens.append(t)
            else:
                # Strip quotes if present
                if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
                    t = t[1:-1]
                tokens.append(t.lower())

        return tokens

    def _build_ast(self, query: str):
        tokens = self._tokenize(query)
        if not tokens:
            return None

        # Parse tokens into AST
        # Simple recursive descent parser

        self._token_idx = 0
        self._tokens = tokens

        try:
            return self._parse_or()
        except Exception:
            # Fallback: if parsing fails, treat the whole query as a single lowercase string to match
            return query.lower()

    def _peek(self):
        if self._token_idx < len(self._tokens):
            return self._tokens[self._token_idx]
        return None

    def _consume(self):
        if self._token_idx < len(self._tokens):
            token = self._tokens[self._token_idx]
            self._token_idx += 1
            return token
        return None

    def _parse_or(self):
        left = self._parse_and()
        while self._peek() == 'OR':
            self._consume()
            right = self._parse_and()
            left = ('OR', left, right)
        return left

    def _parse_and(self):
        left = self._parse_unary()
        while True:
            peek = self._peek()
            if peek == 'AND':
                self._consume()
                right = self._parse_unary()
                left = ('AND', left, right)
            elif peek is not None and peek not in ('OR', ')', 'AND', 'NOT'):
                # Implicit AND
                right = self._parse_unary()
                left = ('AND', left, right)
            else:
                break
        return left

    def _parse_unary(self):
        if self._peek() == 'NOT':
            self._consume()
            return ('NOT', self._parse_primary())
        return self._parse_primary()

    def _parse_primary(self):
        token = self._consume()
        if token == '(':
            expr = self._parse_or()
            if self._peek() == ')':
                self._consume()
            return expr
        elif token is not None and token not in ('AND', 'OR', 'NOT', ')', '('):
            return token
        else:
            # invalid syntax, just return empty string to match nothing/everything harmlessly
            return ""
