# Copyright 2022  Michael Davidsaver
# SPDX-License-Identifier: BSD
# See LICENSE
import os
from functools import partial

from distutils.ccompiler import (new_compiler as _new_compiler, gen_preprocess_options, CCompiler)
from distutils.dep_util import newer
from distutils.errors import DistutilsExecError, CompileError
from distutils.sysconfig import customize_compiler
from distutils import log

__all__ = (
    'new_compiler',
)


# workaround for https://github.com/pypa/setuptools/issues/3591
# cf. https://github.com/mdavidsaver/setuptools_dso/issues/23
#
# setuptools >=63.4.3
# each call to CCompiler.compile(..., include_dirs=None) appends to the
# self.include_dirs list, growing without bound.
# With MSVC this eventually fails.
def _patch_fix_compile_args(realfn, output_dir, macros, include_dirs, *args, **kws):
    log.warn('_patch_fix_compile_args include_dirs=%r', include_dirs)
    return realfn(output_dir, macros, include_dirs or [], *args, **kws)

def _default_preprocess(self, *args, **kws):
    """preprocess() is documented to raise PreprocessError but the
    default (circa py3.9) impl. is a no-op, and the 'unix' impl.
    raises CompileError.  Always a pleasure to find accurate
    documentation...
    """
    raise CompileError("preprocess() not implemented")

def _msvc_preprocess(self, source, output_file=None, macros=None,
                     include_dirs=None, extra_preargs=None, extra_postargs=None):
    """Replacement for default (no-op) distutils.msvccompiler.MSVCCompiler.preprocess()
    """
    # validate and normalize
    ignore, macros, include_dirs = self._fix_compile_args(None, macros, include_dirs)
    # translate macros/include_dirs into -D/-U/-I strings
    pp_args = [self.preprocessor] + gen_preprocess_options(macros, include_dirs)
    # output to file or stdout
    if output_file:
        pp_args.extend(['/P', '/Fi'+output_file])
    else:
        pp_args.extend(['/E'])
    if extra_preargs:
        pp_args[:0] = extra_preargs
    if extra_postargs:
        pp_args.extend(extra_postargs)
    pp_args.append('/TP') # treat as c++
    pp_args.append(source)

    if self.force or output_file is None or newer(source, output_file):
        if output_file:
            self.mkpath(os.path.dirname(output_file))
        try:
            self.spawn(pp_args)
        except DistutilsExecError as msg:
            raise CompileError(msg)

def new_compiler(**kws):
    """Returns a instance of a sub-class of distutils.ccompiler.CCompiler
    """
    compiler = _new_compiler(**kws)
    customize_compiler(compiler)

    if hasattr(compiler.__class__, 'include_dirs'):
        log.warn('Patch _fix_compile_args() to avoid modification to compiler.include_dirs')
        compiler._fix_compile_args = partial(_patch_fix_compile_args, compiler._fix_compile_args)

    if compiler.compiler_type=='msvc': # either msvccompiler or msvc9compiler
        if not compiler.initialized: # extra super lazy initialization...
            compiler.initialize()    # populates self.cc among others

        if compiler.__class__.preprocess is CCompiler.preprocess:
            # default impl. is a no-op...
            compiler.preprocess = partial(_msvc_preprocess, compiler)

        if getattr(compiler, 'preprocessor', None) is None:
            compiler.preprocessor = compiler.cc

    else:
        if compiler.__class__.preprocess is CCompiler.preprocess:
            compiler.preprocess = _default_preprocess

    return compiler
