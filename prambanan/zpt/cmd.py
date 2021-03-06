import prambanan.compiler.astng_patch
from StringIO import StringIO
import argparse
import gettext
import sys
from logilab.astng import nodes
import os
import pkg_resources
from ..jsbeautifier import beautify
from prambanan.cmd import patch_astng_manager
from prambanan.compiler import translate, ImportFinder
from prambanan.compiler.manager import PrambananManager
from prambanan.zpt.compiler.ptparser import PTParser, DependencyOnlyParser

def create_translate_parser():
    parser = argparse.ArgumentParser(
        description="Compile tal template to javascript.")

    parser.add_argument("-o", "--output",
        type=argparse.FileType('w'), default=sys.stdout,
        help="output file, or std output if empty")

    parser.add_argument("-t", "--target", dest="target",
        default = "", type=str,
        help="js target")

    parser.add_argument("-l", "--locale-languange", dest="locale_language",
        default = None, type=str,
        help="target languange")
    parser.add_argument("--locale-domain", dest="locale_domain",
        default = None, type=str,
        help="locale domain, default=as modname")
    parser.add_argument("--locale-dir", dest="locale_dir",
        default = None, type=str,
        help="locale directory default = pkg_resource of modname")

    parser.add_argument("--no-beautify", action="store_false", dest="beautify",
        help="don't beautify result")

    parser.add_argument("package", metavar="package", type=str,
        help="python package")

    parser.add_argument("files", metavar="files", type=str,
        nargs="*",
        help="file if empty all .pt file in the package")

    return parser

def make_visit(package, filename):
    def zpt_visit_module(self, mod):
        """
        Initial node.
        There is and can be only one Module node.

        """
        self.curr_scope = self.mod_scope

        self.change_buffer(self.HEADER_BUFFER)

        self.write("prambanan.load('%s:%s', function(%s) {" % (package, filename, self.lib_name))
        self.change_buffer(self.BODY_BUFFER)


        for stmt in mod.body:
            self.visit(stmt)
            if not isinstance(stmt, nodes.Import) and not isinstance(stmt, nodes.From) and not isinstance(stmt, nodes.Pass):
                self.write_semicolon(stmt)

        self.public_identifiers.append("render")

        get_name = lambda name: name if name not in self.translated_names else self.translated_names[name]
        exported = (self.exe_first_differs(sorted(set(self.public_identifiers)), rest_text=",",
            do_visit=lambda name: self.write("%s: %s" % (name, get_name(name)))))

        self.write("%s.templates.zpt.export('%s','%s', render);});" % (self.lib_name, package, filename))

        builtin_var = None
        builtins = set(self.mod_scope.all_used_builtins())
        if len(builtins) > 0:
            builtin_var = self.curr_scope.generate_variable("__builtin__")
            for builtin in builtins:
                if self.modname != "__builtin__" or builtin not in self.public_identifiers:
                    self.curr_scope.declare_variable(builtin)

        self.change_buffer(self.HEADER_BUFFER)
        self.write_variables()

        if len(builtins) > 0:
            self.write("%s = %s.import('__builtin__');" %(builtin_var, self.lib_name))
            for builtin in builtins:
                if self.modname != "__builtin__" or builtin not in self.public_identifiers:
                    self.write("%s = %s.%s;" %(builtin, builtin_var, builtin))

        for item in self.util_names.values():
            name, value = item
            self.write("%s = %s;" %(name, value))

        self.flush_all_buffer()
        self.curr_scope = None
    return zpt_visit_module

def translate_code(translate_args, manager, output, code, package, path):

    #input
    lines = code.splitlines()

    #i18n translator
    translator = None
    if translate_args.locale_language is not None:
        lang = translate_args.locale_language
        locale_domain = translate_args.locale_domain
        locale_dir = translate_args.locale_dir
        if locale_domain is None:
            locale_domain = package
        if locale_dir is None:
            try:
                locale_dir = pkg_resources.resource_filename(locale_domain, "locale/")
            except ImportError:
                pass
        if locale_dir is not None:
            try:
                translator = gettext.translation(locale_domain, locale_dir, [lang]).gettext
            except IOError:
                pass

    if translator is None:
        translator = gettext.NullTranslations().gettext


    config = {
        "output": output,
        "target": translate_args.target,
        "modname": "",
        "input_name": path,
        "input_path": path,
        "input_lines": lines,
        "input": code,
        "translator": translator,
        "visit_module": make_visit(package,path)
        }

    translate(config, manager)

def generate(translate_args, output_manager, manager, configs):
    package, path = configs
    template_file = pkg_resources.resource_filename(package, path)
    name,ext = os.path.splitext(path)
    preferred_name = "zpt.%s.%s" % (package, name.replace("/", "."))

    out_file = output_manager.add(template_file, preferred_name)
    if not manager.is_file_changed(template_file) and output_manager.is_output_exists(template_file):
        return

    output_manager.start(out_file)
    parser = PTParser(template_file, binds=True)

    output = StringIO() if translate_args.beautify else output_manager.out
    translate_code(translate_args, manager, output, parser.code, package, path)
    if translate_args.beautify:
        output_manager.out.write(beautify(output.getvalue()))

    output_manager.stop()
    manager.mark_file_processed(template_file)

def get_imports(package, path):
    template_file = pkg_resources.resource_filename(package, path)
    parser = DependencyOnlyParser(template_file, binds=False)
    results = ImportFinder.string_find_imports(parser.code)
    results.add("prambanan.zpt")
    return results

def template_changed(output_manager, manager, configs):
    package, path = configs
    template_file = pkg_resources.resource_filename(package, path)
    name,ext = os.path.splitext(path)
    preferred_name = "zpt.%s.%s" % (package, name.replace("/", "."))

    output_manager.add(template_file, preferred_name)
    if not manager.is_file_changed(template_file) and output_manager.is_output_exists(template_file):
        return False
    return True


def find_all_templates(package):
    dir = pkg_resources.resource_filename(package, "")
    for dirname, dirnames, filenames in os.walk(dir):
        for filename in filenames:
            name, ext = os.path.splitext(filename)
            if ext == ".pt":
                abspath = os.path.join(dirname, filename)
                yield os.path.relpath(abspath, dir), abspath

def get_all(args):
    if len(args.files) == 0:
        for result in find_all_templates(args.package):
            yield args.package, result
    else:
        for file in args.files:
            yield args.package, file, pkg_resources.resource_filename(args.package, file)


def main(argv=sys.argv[1:]):
    compile = True
    parser = create_translate_parser()
    args = parser.parse_args(argv)
    manager = PrambananManager([])
    patch_astng_manager(manager)
    for package, name, filename in get_all(args):
        parser = PTParser(filename, binds=True)
        output = StringIO()
        if compile:
            translate_code(args, manager, output,  parser.code, package, name)
            output = beautify(output.getvalue()) if args.beautify else output.getvalue()
            args.output.write(parser.code)
            print "---"
            print "---"
            args.output.write(output)
        else:
            args.output.write(parser.code)
        args.output.close()
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)

