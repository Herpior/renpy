# This file ensures that renpy packages will be imported in the right
# order.

# Some version numbers and things.

# Be sure to change script_version in the demo game, too!
version = "Ren'Py 5.6pre1"
script_version = 5003000
savegame_suffix = "-5.6.0.save"


def import_all():

    import renpy.game

    # Should probably be early, as we will add it as a base to serialized things.
    import renpy.object 

    # Adds in the Ren'Py loader.
    import renpy.loader

    import renpy.ast
    import renpy.curry
    import renpy.easy
    import renpy.execution
    import renpy.loadsave
    import renpy.parser
    import renpy.python # object
    import renpy.script
    import renpy.style

    import renpy.display
    import renpy.display.presplash
    import renpy.display.module
    import renpy.display.render # Most display stuff depends on this.
    import renpy.display.core # object
    import renpy.display.text # core
    import renpy.display.layout # core
    import renpy.display.behavior # layout
    import renpy.display.transition # core
    import renpy.display.im
    import renpy.display.image # core, behavior, im
    import renpy.display.video
    import renpy.display.focus
    import renpy.display.anim
    import renpy.display.particle
    import renpy.display.joystick
    import renpy.display.minigame

    # Note: For windows to work, renpy.audio.audio needs to be after
    # renpy.display.module. 
    import renpy.audio.audio
    import renpy.audio.sound
    import renpy.audio.music

    import renpy.ui

    import renpy.lint
    import renpy.warp

    import renpy.exports
    import renpy.character # depends on exports.

    import renpy.config # depends on lots.
    import renpy.store  # depends on everything.
    import renpy.main

    # Import everything into renpy.exports, provided it isn't
    # already there.
    for k, v in globals().iteritems():
        vars(renpy.exports).setdefault(k, v)

# This reloads all modules.
def reload_all():

    # Cleans out the RenpyImporter.
    import sys
    sys.meta_path.pop()

    import renpy

    # Clears out the module, then reloads it.
    def myreload(mod):
        newdict = dict([(k, v) for k, v in mod.__dict__.iteritems()
                        if k.startswith("__")])

        mod.__dict__.clear()
        mod.__dict__.update(newdict)
        reload(mod)


    myreload(renpy.game)

    # Should probably be early, as we will add it as a base to serialized things.
    myreload(renpy.object)

    # Adds in the Ren'Py loader.
    myreload(renpy.loader)

    myreload(renpy.ast)
    myreload(renpy.curry)
    myreload(renpy.execution)
    myreload(renpy.loadsave)
    myreload(renpy.parser)
    myreload(renpy.python) # object
    myreload(renpy.script)
    myreload(renpy.style)

    myreload(renpy.display.presplash)
    myreload(renpy.display.module)
    myreload(renpy.display.render) # Most display stuff depends on this.
    myreload(renpy.display.core) # object
    myreload(renpy.display.text) # core
    myreload(renpy.display.layout) # core
    myreload(renpy.display.behavior) # layout
    myreload(renpy.display.transition) # core
    myreload(renpy.display.im)
    myreload(renpy.display.image) # core, behavior, im
    myreload(renpy.display.video)
    myreload(renpy.display.focus)
    myreload(renpy.display.anim)
    myreload(renpy.display.particle)
    myreload(renpy.display.joystick)
    myreload(renpy.display.minigame)

    # Note: For windows to work, renpy.audio.audio needs to be after
    # renpy.display.module. 
    myreload(renpy.audio.audio)
    myreload(renpy.audio.sound)
    myreload(renpy.audio.music)

    myreload(renpy.ui)

    myreload(renpy.lint)
    myreload(renpy.warp)

    myreload(renpy.exports)
    myreload(renpy.character)

    myreload(renpy.config)
    myreload(renpy.store)
    myreload(renpy.main)

    # Myreload(everything into renpy.exports, provided it isn't
    # already there.
    for k, v in globals().iteritems():
        vars(renpy.exports).setdefault(k, v)

