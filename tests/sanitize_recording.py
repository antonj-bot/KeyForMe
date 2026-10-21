import ast
import sys
from pathlib import Path


class RecordingSanitizer(ast.NodeTransformer):
    def visit_Expr(self, node):
        # Remove navigation and login-related actions.
        source = ast.unparse(node).lower()

        if any(word in source for word in (
            "password",
            "username",
            "login",
            "sign in",
            "signin",
        )):
            return None

        return self.generic_visit(node)

    def visit_Call(self, node):
        self.generic_visit(node)

        if isinstance(node.func, ast.Attribute):
            method = node.func.attr

            # Replace typed values.
            if method in (
                "fill",
                "press_sequentially",
                "type",
            ):
                if node.args:
                    node.args[0] = ast.Constant(value="TEST")

            # Keep select_option(), check(), click(),
            # and other interactions unchanged.

        return node


def sanitize_recording(source_path):
    source_path = Path(source_path)

    tree = ast.parse(
        source_path.read_text(encoding="utf-8")
    )

    sanitized = RecordingSanitizer().visit(tree)
    ast.fix_missing_locations(sanitized)

    output_path = source_path.with_name(
        source_path.stem + "_clean.py"
    )

    output_path.write_text(
        ast.unparse(sanitized),
        encoding="utf-8",
    )

    print(f"Sanitized recording saved: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python tests/sanitize_recording.py "
            "recorded_nm_form.py"
        )

    sanitize_recording(sys.argv[1])