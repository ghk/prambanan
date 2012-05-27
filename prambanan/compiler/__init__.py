from StringIO import StringIO
from exceptions import SyntaxError
from logilab.astng import nodes, builder
import os
from .scopegenerator import ScopeGenerator
from .target import targets
from .utils import ParseError
from .import_finder import ImportFinder

class Module(object):
    def __init__(self, dependencies):
        if dependencies is None:
            dependencies = []
        self.dependencies = dependencies

class JavascriptModule(Module):
    def __init__(self, paths, dependencies=None):
        if isinstance(paths, str):
            paths = [paths]
        self.paths = paths
        super(JavascriptModule, self).__init__(dependencies)

    def files(self):
        for path in self.paths:
            yield ("js", path, None)

class PythonModule(Module):
    def __init__(self, path, namespace):
        self.path = path
        self.namespace = namespace
        super(PythonModule, self).__init__(ImportFinder.find_imports(path, namespace))

    def files(self):
        yield ("py", self.path, self.namespace)

class DirectoryModule(Module):
    def __init__(self, children, dependencies=None):
        self.children = children
        super(DirectoryModule, self).__init__(dependencies)

    @staticmethod
    def load(dir, dependencies=None):
        config = os.path.abspath(os.path.join(dir, "__prambanan__.py"))
        glbl = {"__file__": config}
        execfile(config, glbl)
        children = glbl["children"]
        return DirectoryModule(children, dependencies)

    def files(self):
        for child in self.children:
            for child_item in child.files():
                yield child_item

def files_to_modules(files, base_directory):
    for file in  files:
        if os.path.isdir(file):
            yield DirectoryModule.load(file)
        else:
            base_name = os.path.basename(file)
            name, ext = os.path.splitext(base_name)
            if ext == ".py":
                dir_name = os.path.dirname(os.path.abspath(file))
                rel_dir = os.path.dirname(os.path.relpath(file, base_directory))
                base_namespace = ".".join(os.path.split(rel_dir))[1:]
                module_name = name if name != "__init__" else os.path.basename(dir_name)
                namespace = module_name if base_namespace == "" else "%s.%s" % (base_namespace, module_name)
                yield PythonModule(file, namespace)
            elif ext == ".js":
                yield JavascriptModule(file)
            else:
                raise ValueError("extension not recognized: %s for file %s" % (ext, file))


def py_visit_module(self, mod):
    """
    Initial node.
    There is and can be only one Module node.

    """
    self.curr_scope = self.mod_scope

    if not self.bare:
        self.change_buffer(self.HEADER_BUFFER)
        if mod.doc:
            self.write_docstring(self.mod_scope.docstring)

        self.write("(function(%s) {" % self.LIB_NAME)
        self.change_buffer(self.BODY_BUFFER)

        public_identifiers = self.mod_scope.module_all
        not_all_exists = public_identifiers is None
        if not_all_exists:
            public_identifiers = []

    for k, v in self.export_map.items():
        self.mod_scope.declare_variable(k)
        self.write("%s = %s.%s;" % (k, self.LIB_NAME, v))

    for stmt in mod.body:
        if isinstance(stmt, nodes.Assign) and len(stmt.targets) == 1 and\
           isinstance(stmt.targets[0], nodes.Name) and\
           stmt.targets[0].name in ("__all__", "__license__"):
            continue
        """
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Str):
            continue # Module docstring
        """

        if not self.bare and not_all_exists:
            for name in self.get_identifiers(stmt):
                if name is not None and not name.startswith("_"):
                    public_identifiers.append(name)

        self.visit(stmt)
        if not isinstance(stmt, nodes.Import) and not isinstance(stmt, nodes.From) and not isinstance(stmt, nodes.Pass):
            self.write_semicolon(stmt)

    if not self.bare:
        self.public_identifiers.extend(public_identifiers)

        get_name = lambda name: name if name not in self.translated_names else self.translated_names[name]
        exported = (self.exe_first_differs(sorted(set(self.public_identifiers)), rest_text=",",
            do_visit=lambda name: self.write("%s: %s" % (name, get_name(name)))))

        self.write("%s.exports('%s',{%s});})(%s);" % (self.LIB_NAME, self.namespace, exported, self.LIB_NAME))

    builtin_var = None
    builtins = set(self.mod_scope.all_used_builtins())
    if len(builtins) > 0:
        builtin_var = self.curr_scope.generate_variable("__builtin__")
        for builtin in builtins:
            if self.namespace != "__builtin__" or builtin not in self.public_identifiers:
                self.curr_scope.declare_variable(builtin)

    self.change_buffer(self.HEADER_BUFFER)
    self.write_variables()

    if len(builtins) > 0:
        self.write("%s = %s.import('__builtin__');" %(builtin_var, self.LIB_NAME))
        for builtin in builtins:
            if self.namespace != "__builtin__" or builtin not in self.public_identifiers:
                self.write("%s = %s.%s;" %(builtin, builtin_var, builtin))

    for item in self.util_names.values():
        name, value = item
        self.write("%s = %s;" %(name, value))

    self.flush_all_buffer()
    self.curr_scope = None


def translate_string(input,namespace="", target=None):
    config = {}
    output = StringIO()
    config["bare"] = True
    config["input_name"] = None
    config["input_lines"] = [input]
    config["output"] = StringIO()
    config["namespace"] = namespace
    config["use_throw_helper"] = True
    config["warnings"] = False
    config["use_throw_helper"] = False

    try:
        tree = nodes.parse(input)
    except SyntaxError as e:
        raise ParseError(e.msg, e.lineno, e.offset, True)

    scope_gen = ScopeGenerator(config["namespace"], tree)

    direct_handlers = {"module": py_visit_module}
    moo = targets.get_translator(target)(scope_gen.root_scope, direct_handlers, config)
    moo.walk(tree)
    return config["output"].getvalue()


def translate(config):
    try:
        tree = builder.ASTNGBuilder().string_build(config["input"], config["input_name"])
        scope_gen = ScopeGenerator(config["namespace"], tree)
        scope_gen.visit(tree)

        direct_handlers = {"module": py_visit_module}
        target = config.get("target", None)
        moo = targets.get_translator(target)(scope_gen.root_scope, direct_handlers, config)
        moo.walk(tree)
        return scope_gen.root_scope.imported_modules()
    except ParseError as e:
        e.input_lines = config["input_lines"]
        e.input_name = config["input_name"]
        raise e
    except SyntaxError as e:
        raise ParseError(e.msg, e.lineno, e.offset, True, config["input_lines"], config["input_name"])