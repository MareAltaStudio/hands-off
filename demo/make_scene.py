"""Build the Blender scene the "user" works on in the demo (run inside Blender):

    blender --background --factory-startup --python make_scene.py -- out/scene.blend

A subdivided monkey and three cubes with more and more edge loops, the same subject the
agent reads about in the manual on the other monitor.
"""

import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)

bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 1.2))
monkey = bpy.context.object
monkey.modifiers.new("Subdivision", "SUBSURF").levels = 2
bpy.ops.object.shade_smooth()

for i, cuts in enumerate((0, 1, 3)):
    bpy.ops.mesh.primitive_cube_add(size=0.9, location=(-1.6 + i * 1.6, -2.2, 0.45))
    cube = bpy.context.object
    if cuts:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.subdivide(number_cuts=cuts)
        bpy.ops.object.mode_set(mode="OBJECT")
    cube.modifiers.new("Subdivision", "SUBSURF").levels = 2

bpy.ops.mesh.primitive_plane_add(size=12, location=(0, -1, 0))
bpy.ops.object.select_all(action="DESELECT")
monkey.select_set(True)
bpy.context.view_layer.objects.active = monkey

for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.type = "SOLID"
                    space.shading.light = "MATCAP"
                    space.overlay.show_wireframes = True
                    space.overlay.wireframe_threshold = 0.6

bpy.ops.wm.save_as_mainfile(filepath=out)
print("saved", out)
