# This file contains code that handles the execution of python code
# contained within the script file. It also handles rolling back the
# game state to some time in the past.


from compiler import parse
from compiler.pycodegen import ModuleCodeGenerator, ExpressionCodeGenerator
# from compiler.misc import set_filename
import compiler.ast as ast

import marshal
import random
import types
import weakref
import sets
import sys

import renpy

##### Code that computes reachable objects, which is used to filter
##### the rollback list before rollback or serialization.

def reached(obj, path, reachable):
    """
    @param obj: The object that was reached.
    @param path: The path from the store via which it was reached.
    @param reachable: A map from reachable object id to path.
    """

    if id(obj) in reachable:
        return

    reachable[id(obj)] = path

    # print id(obj), repr(obj), path
    
    try:
        # Treat as fields, indexed by strings.
        for k, v in vars(obj).iteritems():
            reached(v, path + "." + k, reachable)
    except:
        pass

    try:
        if not isinstance(obj, basestring):
            # Treat as iterable
            for i, v in enumerate(obj):
                reached(v, path + "[" + str(i) + "]", reachable)
    except:
        pass
        

    try:
        # Treat as dict.
        for k, v in obj.iteritems():
            mypath = path + "[" + repr(k) + "]"
            # Keys will be handled by iterable code.
            reached(v, mypath, reachable)
    except:
        pass

            
def reached_vars(store, reachable):
    """
    Marks everything reachable from the variables in the store
    or from the context info objects as reachable.
    
    @param store: A map from variable name to variable value.
    @param reachable: A dictionary mapping reached object ids to
    the path by which the object was reached.
    """

    for k, v in store.iteritems():
        reached(v, k, reachable)    
    
    for c in renpy.game.contexts:
        reached(c.info, "#context", reachable)


##### Code that replaces literals will calls to magic constructors.

def wrap_node(n):
    """
    Replaces literal lists and dictionaries, and list comprehensions,
    with calls to the appropriate Ren'Py constructors.
    """

    if isinstance(n, (ast.List, ast.ListComp)):
        n = ast.CallFunc(node=ast.Name('__renpy__list__'),
                         args=[ n ],
                         star_args=None,
                         dstar_args=None,
                         )

    elif isinstance(n, ast.Dict):
        n = ast.CallFunc(node=ast.Name('__renpy__dict__'),
                         args=[ n ],
                         star_args=None,
                         dstar_args=None,
                         )

    return n


def recursively_replace(o, func):
    """
    Walks through a compiler AST, calling the supplied function when a
    node is encountered, and replacing the node with the return value.
    """

    if isinstance(o, list):
        return [ recursively_replace(i, func) for i in o ]

    if isinstance(o, tuple):
        return tuple([ recursively_replace(i, func) for i in o ])

    if isinstance(o, ast.Node):
        for k in vars(o):
            setattr(o, k, recursively_replace(getattr(o, k), func))

        return func(o)

    return o

def set_filename(filename, offset, tree):
    """Set the filename attribute to filename on every node in tree"""
    worklist = [tree]
    while worklist:
        node = worklist.pop(0)
        node.filename = filename

        lineno = getattr(node, 'lineno', None)
        if lineno is not None:
            node.lineno = lineno + offset

        worklist.extend(node.getChildNodes())


def py_compile(source, mode, filename='<none>', lineno=1):
    """
    Compiles the given source code using the supplied codegenerator.
    Lists, List Comprehensions, and Dictionaries are wrapped when
    appropriate.

    @param source: The sourccode, as a string.

    @param mode: 'exec' or 'eval'.

    @param filename: The filename that the source code is taken from.

    @param lineno: The line number of the first line of the source code.
    """

    source = source.encode('raw_unicode_escape')
    try:
        tree = parse(source, mode)
    except SyntaxError, e:
        e.lineno += lineno - 1
        raise
    
    recursively_replace(tree, wrap_node)

    if mode == 'exec':
        set_filename(filename, lineno - 1, tree)
        cg = ModuleCodeGenerator(tree)
    else:
        set_filename(filename, lineno - 1, tree)
        cg = ExpressionCodeGenerator(tree)

    return cg.getCode()

def py_compile_exec_bytecode(source, **kwargs):
    code = py_compile(source, 'exec', **kwargs)
    return marshal.dumps(code)

def py_compile_eval_bytecode(source, **kwargs):
    source = source.strip()
    code = py_compile(source, 'eval', **kwargs)
    return marshal.dumps(code)



##### Classes that are exported in place of the normal list, dict, and
##### object.

def mutator(method):

    def do_mutation(self, *args, **kwargs):

        mutated = renpy.game.log.mutated

        if id(self) not in mutated:
            mutated[id(self)] = ( weakref.ref(self), self.get_rollback())

        return method(self, *args, **kwargs)

    return do_mutation

class RevertableList(list):

    __delitem__ = mutator(list.__delitem__)
    __delslice__ = mutator(list.__delslice__)
    __setitem__ = mutator(list.__setitem__)
    __iadd__ = mutator(list.__iadd__)
    __imul__ = mutator(list.__imul__)
    append = mutator(list.append)
    extend = mutator(list.extend)
    insert = mutator(list.insert)
    pop = mutator(list.pop)
    remove = mutator(list.remove)
    reverse = mutator(list.reverse)
    sort = mutator(list.sort)

    def wrapper(method):
        def newmethod(*args, **kwargs):
            return RevertableList(method(*args, **kwargs))

        return newmethod

    __add__ = wrapper(list.__add__)
    __getslice__ = wrapper(list.__getslice__)
    __mul__ = wrapper(list.__mul__)

    # TODO: Handle __iter__ (or not).
    def get_rollback(self):
        return self[:]

    def rollback(self, old):
        self[:] = old

class RevertableDict(dict):

    __delitem__ = mutator(dict.__delitem__)
    __setitem__ = mutator(dict.__setitem__)
    clear = mutator(dict.clear)
    pop = mutator(dict.pop)
    popitem = mutator(dict.popitem)
    setdefault = mutator(dict.setdefault)

    def copy(self):
        rv = RevertableDict()
        rv.update(self)
        return rv

    def get_rollback(self):
        return self.items()

    def rollback(self, old):
        self.clear()

        for k, v in old:
            self[k] = v

class RevertableSet(sets.Set):

    __iand__ = mutator(sets.Set.__iand__)
    __ior__ = mutator(sets.Set.__ior__)
    __isub__ = mutator(sets.Set.__isub__)
    __ixor__ = mutator(sets.Set.__ixor__)
    add = mutator(sets.Set.add)
    clear = mutator(sets.Set.clear)
    difference_update = mutator(sets.Set.difference_update)
    discard = mutator(sets.Set.discard)
    intersection_update = mutator(sets.Set.intersection_update)
    pop = mutator(sets.Set.pop)
    remove = mutator(sets.Set.remove)
    symmetric_difference_update = mutator(sets.Set.symmetric_difference_update)
    union_update = mutator(sets.Set.union_update)
    update = mutator(sets.Set.update)

    # TODO: Wrap all of the methods that can return normal sets.

    def wrapper(method):
        def newmethod(*args, **kwargs):
            rv = method(*args, **kwargs)
            if isinstance(rv, sets.Set):
                return RevertableSet(rv)
            else:
                return rv

        return newmethod

    __and__ = wrapper(sets.Set.__and__)
    __copy__ = wrapper(sets.Set.__copy__)
    __deepcopy__ = wrapper(sets.Set.__deepcopy__)
    __sub__ = wrapper(sets.Set.__sub__)
    __xor__ = wrapper(sets.Set.__xor__)
    __or__ = wrapper(sets.Set.__or__)
    copy = wrapper(sets.Set.copy)
    difference = wrapper(sets.Set.difference)
    intersection = wrapper(sets.Set.intersection)
    symmetric_difference = wrapper(sets.Set.symmetric_difference)
    union = wrapper(sets.Set.union)

    del wrapper

    def get_rollback(self):
        return list(self)

    def rollback(self, old):
        sets.Set.clear(self)
        sets.Set.update(self, old)
    

class RevertableObject(object):

    def __setattr__(self, attr, value):
        import sys
        object.__setattr__(self, attr, value)

    def __delattr__(self, attr):
        object.__delattr__(self, attr)

    __setattr__ = mutator(__setattr__)
    __delattr__ = mutator(__delattr__)

    def get_rollback(self):
        return self.__dict__.copy()

    def rollback(self, old):
        self.__dict__.clear()
        self.__dict__.update(old)

##### An object that handles deterministic randomness, or something.

class DetRandom(random.Random):

    def __init__(self):
        super(DetRandom, self).__init__()
        self.stack = [ ]

    def random(self):

        if self.stack:
            rv = self.stack.pop()
        else:
            rv = super(DetRandom, self).random()            

        renpy.game.log.current.random.append(rv)
        return rv

    def pushback(self, l):
        """
        Pushes the random numbers in l onto the stack so they will be generated
        in the order given.
        """

        ll = l[:]
        ll.reverse()

        self.stack.extend(ll)
        
    def reset(self):
        """
        Resets the RNG, removing all of the pushbacked numbers.
        """

        self.stack = [ ]

rng = DetRandom()

##### This is the code that actually handles the logging and managing
##### of the rollbacks.

class Rollback(renpy.object.Object):
    """
    Allows the state of the game to be rolled back to the point just
    before a node began executing.

    @ivar context: A shallow copy of the context we were in before
    we started executing the node. (Shallow copy also includes
    a copy of the associated SceneList.)

    @ivar objects: A list of tuples, each containing an object and a
    token of information that, when passed to the rollback method on
    that object, causes that object to rollback.

    @ivar store: A list of updates to store that will cause the state
    of the store to be rolled back to the start of node
    execution. This is a list of tuples, either (key, value) tuples
    representing a value that needs to be assigned to a key, or (key,)
    tuples that mean the key should be deleted.

    @ivar checkpoint: True if this is a user-visible checkpoint,
    false otherwise.

    @ivar purged: True if purge_unreachable has already been called on
    this Rollback, False otherwise.

    @ivar random: A list of random numbers that were generated during the
    execution of this element.
    """

    def __init__(self):
        self.context = renpy.game.contexts[0].rollback_copy()
        self.objects = [ ]
        self.store = [ ]
        self.checkpoint = False
        self.purged = False
        self.random = [ ]

    def purge_unreachable(self, reachable):
        """
        Adds objects that are reachable from the store of this
        rollback to the set of reachable objects, and purges
        information that is stored about totally unreachable objects.

        Returns True if this is the first time this method has been
        called, or False if it has already been called once before.        
        """

        if self.purged:
            return False

        self.purged = True

        # Add objects reachable from the store.
        for i in self.store:
            if len(i) != 2:
                continue

            k, v = i
            reached(v, k, reachable)

        # Purge object update information for unreachable objects.
        new_objects = [ ]

        for o, rb in self.objects:
            if id(o) in reachable:
                new_objects.append((o, rb))
            else:
                if renpy.config.debug:
                    print "Removing unreachable:", o
                pass
                
        self.objects = new_objects

        return True


    def rollback(self):
        """
        This reverts the game state to the state it was in when this
        Rollback was first created.
        """

        for obj, roll in self.objects:
            obj.rollback(roll)

        for t in self.store:
            if len(t) == 2:
                k, v = t
                vars(renpy.store)[k] = v
            else:
                k, = t
                del vars(renpy.store)[k]

        renpy.game.contexts = [ self.context ]
        rng.pushback(self.random)
        

class RollbackLog(renpy.object.Object):
    """
    This class manages the list of Rollback objects.

    @ivar log: The log of rollback objects.

    @ivar current: The current rollback object. (Equivalent to
    log[-1])

    @ivar ever_been_changed: A dictionary containing a key for each
    variable in the store that has ever been changed. (These variables
    become the roots of what is changed or rolled-back.)

    @ivar frozen_roots: A frozen copy of the roots. When freeze is called,
    this holds a copy of roots. It's None at other times.

    @ivar rollback_limit: The number of steps left that we can
    interactively rollback.

    Not serialized:
    
    @ivar old_store: A copy of the store as it was when begin was
    last called.

    @ivar mutated: A dictionary that maps object ids to a tuple of
    (weakref to object, information needed to rollback that object)
    """

    nosave = [ 'old_store', 'mutated' ]

    def __init__(self):
        self.log = [ ]
        self.current = None
        self.mutated = { }
        self.ever_been_changed = { }
        self.frozen_roots = None
        self.rollback_limit = 0

        # Reset the RNG on the creation of a new game.
        rng.reset()

    def after_setstate(self):
        self.mutated = { }

    def begin(self):
        """
        Called before a node begins executing, to indicate that the
        state needs to be saved for rollbacking.
        """

        # If the transient scene list is not empty, then we do
        # not begin a new rollback, as the TSL will be purged
        # after a rollback is complete.
        if not renpy.game.contexts[0].scene_lists.transient_is_empty():
            return

        # If the log is too long, try pruning it to a label.
        if len(self.log) > renpy.config.rollback_length:
            rb = self.log[-renpy.config.rollback_length]

            # Checks to see if this is a real name, rather than a
            # tuple.
            if isinstance(rb.context.current, basestring):
                self.log = self.log[-renpy.config.rollback_length:]

        self.current = Rollback()
        self.log.append(self.current)

        self.mutated = { }
        self.old_store = renpy.store.__dict__.copy()

    def complete(self):
        """
        Called after a node is finished executing, before a save
        begins, or right before a rollback is attempted. This may be
        called more than once between calls to begin, and should always
        be called after an update to the store but before a rollback
        occurs.
        """

        new_store = renpy.store.__dict__
        store = [ ]

        # Find store values that have changed since the last call to
        # begin, and use them to update the store. Also, update the
        # list of store keys that have ever been changed.

        for k, v in self.old_store.iteritems():
            if k not in new_store or new_store[k] is not v:
                store.append((k, v))
                self.ever_been_changed[k] = True

        for k in new_store:
            if k not in self.old_store:
                store.append((k, ))
                self.ever_been_changed[k] = True

        self.current.store = store

        # Update the list of mutated objects, and what we need to do
        # to restore them.
        
        self.current.objects = [ ]
        
        for k, (ref, roll) in self.mutated.iteritems():

            obj = ref()
            if not obj:
                continue

            self.current.objects.append((obj, roll))



    def get_roots(self):
        """
        Return a map giving the current roots of the store. This is a
        map from a variable name in the store to the value of that
        variable. A variable is only in this map if it has ever been
        changed since the init phase finished.
        """

        rv = { }

        store = vars(renpy.store)

        for k in self.ever_been_changed.keys():
            if k in store:
                rv[k] = store[k]

        return rv

    def purge_unreachable(self, roots):
        """
        This is called to purge objects that are unreachable from the
        roots from the object rollback lists inside the Rollback entries.

        This should be called immediately after complete(), so that there
        are no changes queued up.
        """

        reachable = { }

        reached_vars(roots, reachable)

        revlog = self.log[:]
        revlog.reverse()

        for i in revlog:
            if not i.purge_unreachable(reachable):
                break
                

    def checkpoint(self):
        """
        Called to indicate that this is a checkpoint, which means
        that the user may want to rollback to just before this
        node.
        """

        if self.rollback_limit < renpy.config.hard_rollback_limit: 
            self.rollback_limit += 1
        
        self.current.checkpoint = True

    def block(self):
        """
        Called to indicate that the user should not be able to rollback
        through this checkpoint.
        """

        self.rollback_limit = 0

    def rollback(self, checkpoints, force=False, label=None):
        """
        This rolls the system back to the first valid rollback point
        after having rolled back past the specified number of checkpoints.

        If we're currently executing code, it's expected that complete()
        will be called before a rollback is attempted.

        force makes us throw an exception if we can't find a place to stop
        rolling back, otherwise if we run out of log this call has no
        effect.

        @param label: The label that is jumped to in the game script
        after rollback has finished, if it exists.
        """

        # If we have exceeded the rollback limit, and don't have force,
        # give up.
        if not self.rollback_limit > 0 and not force:
            return

        self.rollback_limit -= 1

        self.purge_unreachable(self.get_roots())

        revlog = [ ]

        while self.log:
            rb = self.log.pop()
            revlog.append(rb)

            if rb.checkpoint:
                checkpoints -= 1

            if checkpoints <= 0:
                if renpy.game.script.has_label(rb.context.current):
                    break

        else:
            if force:
                raise Exception("Couldn't find a place to stop rolling back. Perhaps the script changed in an incompatible way?")
                
            # Otherwise, just give up.

            print "Can't find a place to rollback to. Not rolling back."

            revlog.reverse()
            self.log = self.log + revlog
            return

        for rb in revlog:
            rb.rollback()

        # Disable the next transition, as it's pointless.
        renpy.game.interface.suppress_transition = True

        # If necessary, reset the RNG.
        if force:
            rng.reset()

        # Flag that we're in the transition immediately after a rollback.
        renpy.game.after_rollback = True

        # Restart the game with the new state.
        raise renpy.game.RestartException(renpy.game.contexts[:], label)

    def freeze(self):
        """
        This is called to freeze the store and the log, in preparation
        for serialization. The next call on log should either be
        unfreeze (called after a serialization reload) or discard_freeze()
        (called after the save is complete). 
        """
        
        self.complete()
        self.frozen_roots = self.get_roots()
        self.purge_unreachable(self.frozen_roots)

    def discard_freeze(self):
        """
        Called to indicate that we will not be restoring from the
        frozen state.
        """

        self.frozen_roots = None

        # We need to do this to counteract the effects of self.purge_unreachable
        self.current.purged = False

    def unfreeze(self, label=None):
        """
        Used to unfreeze the game state after a load of this log
        object. This call will always throw an exception. If we're
        lucky, it's the one that indicates load was successful.

        @param label: The label that is jumped to in the game script
        after rollback has finished, if it exists.
        """

        # Set us up as the game log.
        renpy.game.log = self
        
        # Restore the store.
        store = renpy.store.__dict__
        store.clear()
        store.update(renpy.game.clean_store)

        for k in self.ever_been_changed:
            if k in store:
                del store[k]

        store.update(self.frozen_roots)
        self.frozen_roots = None

        # Now, rollback to an acceptable point.
        self.rollback(0, force=True, label=label)

        # We never make it this far.

def py_traceback():
    type, value, tb = sys.exc_info()

    while tb:
        f = tb.tb_frame
        line = tb.tb_lineno
        co = f.f_code
        filename = co.co_filename
        
        if filename.endswith(".rpy") and not filename.startswith("common"):
            renpy.game.exception_info += "\nWhile executing python code on line %d of %s." % (line, filename)
                
        tb = tb.tb_next

    

def py_exec_bytecode(bytecode, hide=False):

    store = vars(renpy.store)

    if hide:
        locals = { }
    else:
        locals = store

    try:
        exec marshal.loads(bytecode) in store, locals
    except:
        py_traceback()
        raise

        
def py_exec(source, hide=False, store=None):

    if store is None:
        store = vars(renpy.store)

    if hide:
        locals = { }
    else:
        locals = store

    try:
        exec py_compile(source, 'exec') in store, locals
    except:
        py_traceback()
        raise

def py_eval_bytecode(bytecode):

    return eval(marshal.loads(bytecode), vars(renpy.store))

def py_eval(source):
    source = source.strip()

    return eval(py_compile(source, 'eval'),
                vars(renpy.store))

