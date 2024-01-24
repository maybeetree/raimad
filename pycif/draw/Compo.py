"""Compo.py: contains Compo class, relevant helpers, and Exceptions."""

from io import StringIO
from typing import Any, Type, Self, List, ClassVar, Mapping
import inspect
from copy import deepcopy

import numpy as np

import pycif as pc

log = pc.get_logger(__name__)

# Possibilities:
# None can be used when parent and child have identical layers
# OR when both have only one layer
# str can be used to specify the layername of the parent
# when child has only one layer
# otherwise needs full dict
SubcompoLayermapShorthand = None | str | dict
SubpolyLayerShorthand = None | str

class Compo(pc.Markable, pc.BBoxable):
    """
    Compos: the building blocks of all pycif designs.

    A Compo class consists of:
        - Layers
        - Options
        - Marks
        - the _make function

    Layers define the lithographic layers that a compo class
    places its geometry on.

    Options are customization parameters that users of the compo
    may wish to change.

    Marks are named points in the compo,
    which may be of interest to its users.

    The _make() function contains instructions on how
    to create the compo's geometry based on the Options.

    An instance of a Compo class,
    or a "compo instance" for short,
    contains:
        - Subcompos
        - Subpolys
        - Specific options
        - Specific marks

    Subcompos and Subpolys make up the geometry of each
    compo instance.

    Each Supoly exists on strictly one layer in its parent compo.

    Each Subcompo may have different layers than the parent compo,
    and for this there exists a "layer map",
    which dictates how the geometry of a subcompo gets
    transfered to the parent compo.

    For example, an I-shaped filter may have abstract "Ground"
    and "Dielectric" layers,
    which may be mapped to concrete "Ground plane" and "E-Beam Dielectric"
    layers in the parent compo.

    All instances of a given Compo class
    share the same set of layers,
    but what geometry exists on those layers may be different per compo,
    depending on the Options.

    All instances of a given Compo class
    share the same set of marks,
    but the specific locations of those marks may be different per compo,
    depending on the Options.

    All instances of a given Compo class
    share the same set of options and default values,
    but those default values may be owerwritten
    by whoever is instantiation that Compo to achieve
    a desired outcome.
    """

    class OptionsMeta(type):
        def __iter__(self):
            for parent in self.__mro__:
                if not issubclass(parent, Compo.Options):
                    break

                for name, option in vars(parent).items():
                    if not isinstance(option, pc.Option):
                        continue

                    yield option

    class Options(dict, metaclass=OptionsMeta):
        def __init__(self, values = None):
            for parent in type(self).__mro__:
                if not issubclass(parent, Compo.Options):
                    break

                for name, option in vars(parent).items():
                    if not isinstance(option, pc.Option.Option):
                        continue
                    self[name] = option.default

            if values is None:
                return

            if (unknown_opts := set(values.keys()) - self.keys()):
                raise pc.draw.Option.UnknownOptionSuppliedError(
                    f'Unknown option(s) {unknown_opts}. '
                    f'Known option(s) are {self.keys()}.'
                    )

            for option, value in values.items():
                self[option] = value

    class LayersMeta(type):
        def __iter__(self):
            yield from self().__iter__()

        def __getitem__(self, item):
            return self().__getitem__(item)

    class Layers(tuple, metaclass=LayersMeta):
        _singleton: ClassVar[Self]

        def __new__(cls):
            if not '_singleton' in vars(cls).keys():
                cls._singleton = super().__new__(cls, (
                    layer
                    for parent in cls.__mro__
                        if issubclass(parent, Compo.Layers)
                    for layer in vars(parent).values()
                        if isinstance(layer, pc.Layer)
                    ))

            return cls._singleton

    #class Layers():
    #    """Namespace for layers."""

    #    _layer_names: List[str]

    #    def __init__(self):
    #        """Create empty Layers namespace."""
    #        self._layer_names = [
    #            getattr(self, name)  # get the NAME
    #            for name in dir(type(self))
    #            if not name.startswith('_')
    #            ]

    #        # The usage of `dir` here as opposed to __dict__ is crucial,
    #        # `__dict__` won't include inherited layers, but `dir` does.

    #        if len(self._layer_names) < 1:
    #            log.warning(
    #                f"{self} has no layers"
    #                )

    #    def __iter__(self):
    #        """Get Layers as iter."""
    #        return iter(self._layer_names)

    Modulebrowser_howtoget: ClassVar[str | None] = None
    # Something like 'from pc_Mymodule.Mycompo import Mycompo',
    # otherwise this is autogenerated using inspect.

    # Every compo instance has its own instance of Options,
    # so that Options._options (which stores the actual values for each
    # compo) is unique per compo instance
    options: Options

    # Layers are the same for each compo class,
    # so we store it as a classvar.
    # We could also store the Layers *class*
    # for each Compo class
    # (i.e. ClassVar[Type[Layers]] ),
    # but we don't, for consistency's sake,
    # and also because then the Layer descriptor wouldn't work.
    layers: ClassVar[Layers]

    def __init_subclass__(cls, **kwargs):
        """
        Verify that Compo class is created corresctly.

        1. Check that Options namespace inherits from Compo.Options
        2. Check that Layers namespace inherits from Compo.Layers
        3. Check that Layer objects in Layers namespace are created correctly.
        """
        super().__init_subclass__(**kwargs)

        if not issubclass(cls.Options, Compo.Options):
            raise Exception(
                """`Options` must inherit from Compo.Options"""
                )

        if not issubclass(cls.Layers, Compo.Layers):
            raise Exception(
                """`Layers` must inherit from Compo.Layers"""
                )

        for name, obj in cls.Layers.__dict__.items():
            if isinstance(obj, type) and issubclass(obj, pc.Layer):
                log.warn(
                    f"Compo class {cls},\n"
                    f"layer specification {cls.Layers}\n"
                    f"contains Layer *class* {obj}.\n"
                    f"Did somebody accidentally type {name} = pc.Layer\n"
                    f"instead of {name} = pc.Layer() ??\n"
                    )

    def __init__(self, options=None):
        """
        Create new compo instance.

        Parameters
        ----------
        options: dict
            Set custom options
        """
        super().__init__()

        self.options = self.Options(options)
        self.layers = self.Layers()

        self.subcompos = []
        self.subpolys = []

        self._make()

    def copy(self):
        """Copy the compo instance."""
        # TODO think about this
        return deepcopy(self)

    def add_subcompo(
            self,
            compo,
            layermap_shorthand: SubcompoLayermapShorthand = None,
            ):
        """Add new compo as a subcompo."""
        layermap = parse_subcompo_layermap_shorthand(
            self,
            compo,
            layermap_shorthand,
            )

        subcompo = Subcompo(
            compo,
            layermap,
            )

        # TODO update bbox here?

        self.subcompos.append(subcompo)

    def add_subpoly(
            self,
            poly,
            layermap: SubpolyLayerShorthand = None,
            ):
        """Add new poly as a subpoly."""
        layermap_full = parse_subpoly_layer_shorthand(
            self,
            poly,
   layermap
            )

        subpoly = Subpoly(
            poly,
            layermap_full,
            )

        self.subpolys.append(subpoly)

    def add_subpolys(
            self,
            polys: List[pc.Poly | pc.Group] | pc.Poly | pc.Group,
            layermap: SubpolyLayerShorthand = None,
            ):
        """
        Add multiple subpolys or subpoly groups.
        """
        if isinstance(polys, pc.Poly):
            self.add_subpoly(polys, layermap)

        elif isinstance(polys, pc.Group):
            for poly in polys.get_polys():
                self.add_subpoly(poly, layermap)

        elif isinstance(polys, list | tuple | set):
            # TODO isiterable
            for poly in polys:
                self.add_subpolys(poly, layermap)

        else:
            raise Exception("Please only pass polys or polygroups")

    def get_subpolys(self, layermap=None, do_apply_transform=True):

        if layermap is None:
            layermap = dict(zip(self.layers, self.layers))

        else:
            assert set(layermap.keys()).issubset(self.layers)

        return [
            Subpoly(
                (
                    subpoly.get_poly().apply_transform(self.transform)
                    if do_apply_transform
                    else subpoly.get_poly()
                    ),
                layermap[subpoly.layer]
                )
            for subpoly in [
                *[
                    subpoly_inner
                    for subcompo in self.subcompos
                    for subpoly_inner in subcompo.get_subpolys()
                    ],
                *[
                    subpoly_inner_2.get_subpoly()
                    for subpoly_inner_2 in self.subpolys
                    ]
                ]
            if layermap[subpoly.layer] is not None
            ]

    def _get_subpolys(self):
        return self.get_subpolys(do_apply_transform=False)

    def _get_xyarray(self):
        # TODO slow
        xyarray = []
        for subpoly in self._get_subpolys():
            xyarray.extend(subpoly.poly.get_xyarray())
        return np.array(xyarray)

    def _make(self):
        """
        This method should actually generate all subpolys
        and subcompos.

        This is an abstract base class,
        so here this method actually does nothing.

        opts allows to pass a custom options list

        Note that make() should work with all default parameters.
        This will actually be used for making the preview image.
        """
        raise NotImplementedError

    @classmethod
    def parent(cls):
        """
        Return parent class.
        This is a shorthand for cls.__bases__[0]
        """
        return cls.__bases__[0]

    @classmethod
    def is_interface(cls):
        if cls is Compo:
            print("""Base Compo class is not an interface.""")
            return False

        return (cls.parent() is Compo)

    @classmethod
    def is_interface_of(cls, of: Type[Self]):
        if cls is Compo:
            print("""Base Compo class is not an interface.""")
            return False

        if of is Compo:
            print("""Base Compo class cannot have interfaces""")
            return False

        return issubclass(cls, of)

    @classmethod
    def get_custom_methods(cls):
        """
        Extract custom methods from this compo class.
        For example, automatic connection methods
        from CPWs.
        """
        # TODO can interfaces override or pass through
        # custom methods? How would this work?

        # Maybe we need a special decorator
        # for external methods?

        return {
            attr_name: attr
            for attr_name, attr
            in cls.__dict__.items()
            if not attr_name.startswith('_') and inspect.isfunction(attr)
            }

    def _repr_svg_(self):
        """Export compo as svg. For use in Jupyter notebooks."""
        return pc.export_svg(self)

class Subpoly(object):
    """
    Container that stores a poly and which layer it belongs
    to in the parent
    """
    poly: pc.Poly
    layer: str

    def __init__(self, poly: pc.Poly, layer: str):
        self.poly = poly
        self.layer = layer

    def get_subpoly(self):
        # This is where the polys of the living breathing
        # compo hierarchy get cloned for export.
        return Subpoly(self.poly.copy(), self.layer)

    def get_poly(self):
        # This is where the polys of the living breathing
        # compo hierarchy get cloned for export.
        return self.poly.copy()

class Subcompo(object):
    """
    Container for compo that is part of another compo.
    """
    def __init__(self, compo, layermap):
        self.compo = compo
        self.layermap = layermap

    def get_subpolys(self):
        return [
            Subpoly(subpoly.get_poly(), self.layermap[subpoly.layer])
            for subpoly
            in self.compo.get_subpolys()
            if self.layermap[subpoly.layer] is not None
            ]

def parse_subcompo_layermap_shorthand(parent, child, layermap_shorthand: SubcompoLayermapShorthand):

    parent_layers = set(parent.layers)
    child_layers = set(child.layers)

    if layermap_shorthand is None:
        if child_layers.issubset(parent_layers):
            layermap = dict(zip(child_layers, child_layers))

        elif len(parent_layers) == len(child_layers) == 1:
            # Case One: parent and child the same number of layers
            # TODO this is a bad idea! Can cause confusion later on!!
            log.debug(
                f"Mapping sole layer {child_layers} of {child} "
                f"to sole layer {parent_layers} of {parent} "
                f"because no layermap was specified. "
                )
            layermap = dict(zip(child_layers, parent_layers))

        else:
            raise Exception(
                f"You must specify how to map the layers {child_layers} "
                f"of child compo {child} "
                f"to the layers {parent_layers} "
                f"of parent compo {parent}"
                )

    elif isinstance(layermap_shorthand, str):
        if len(child_layers) != 1:
            raise Exception(
                "You specified an str layermap shorthand, "
                "but the child compo doesn't have "
                "just one layer."
                )

        if layermap_shorthand not in parent_layers:
            raise Exception(
                "You specified an str layermap shorthand, "
                "but that layer is not in the parent compo."
                )

        layermap = {list(child_layers)[0]: layermap_shorthand}

    elif isinstance(layermap_shorthand, dict):
        if not set(layermap_shorthand.keys()).issubset(child_layers):
            raise Exception(
                "Layermap keys are not a subset of child compo layers"
                )

        if not set(layermap_shorthand.values()).issubset(parent_layers):
            raise Exception(
                "Layermap values are not a subset of parent compo layers"
                )

        layermap = layermap_shorthand

    else:
        raise Exception(
            "Layermap shorthand is incorrect type"
            )

    # Pad layermap
    for missing_layer in child_layers - set(layermap):
        log.warning(
            f"throwing away layer {missing_layer} of child compo {child} "
            f"with parent {parent} "
            f"because it was not mentioned in the layermap."
            f"Please explicitly map this layer to None in the future."
            )

        layermap[missing_layer] = None

    return layermap


def parse_subpoly_layer_shorthand(
        parent: Compo,
        child: pc.Poly,
        layer_shorthand: SubpolyLayerShorthand
        ):
    parent_layers = set(parent.layers)

    if layer_shorthand is None:
        if len(parent_layers) == 1:
            sole_layer = list(parent_layers)[0]
            log.debug(
                f"Mapping poly {child} \n"
                f"to sole layer {sole_layer} of {parent} \n"
                f"because no layermap was specified. \n"
                )
            return sole_layer
        else:
            raise Exception(
                f"Could not map poly {child} to \n"
                f"parent compo {parent} \n"
                "because the parent contains multiple layers \n"
                f"({parent_layers}), \n"
                f"and you did not specify which layer this poly "
                f"belongs on."
                )

    elif isinstance(layer_shorthand, str):
        if layer_shorthand in parent_layers:
            return layer_shorthand
        else:
            raise Exception(
                f"Could not map poly {child} to \n"
                f"parent compo {parent} \n"
                f"because the specified layer `{layer_shorthand}` \n"
                f"could not be found in the parent \n"
                f"(valid layers are {parent_layers})."
                )

    else:
        raise Exception(
            "Layermap shorthand is incorrect type"
            )


