import inspect
from copy import deepcopy

import pycif as pc

class MarksContainer(pc.DictList):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._proxy = None

    def __getattr__(self, name):

        if self._proxy is None:
            return self[name]

        return self._proxy.get_mark(name)

    def _proxy_copy(self, proxy):
        new = type(self)({
            key: val for key, val in self.items()
            })
        new._proxy = proxy
        return new

class SubcompoContainer(pc.DictList):
    def _filter(self, item):
        if isinstance(item, pc.Compo):
            return pc.Proxy(item, _autogen=True)
        elif isinstance(item, pc.Proxy):
            return item
        else:
            raise Exception  # TODO actual exception
        # TODO generally need to standardize runtime checks.

class Compo:
    def __init__(self, *args, **kwargs):
        self.geoms = {}
        self.subcompos = SubcompoContainer()
        self.marks = MarksContainer()

        self._make(*args, **kwargs)

    def get_geoms(self) -> dict:
        geoms = self.geoms.copy()
        for subcompo in self.subcompos.values():
            # TODO override "update" method in geoms container?
            for layer_name, layer_geoms in subcompo.get_geoms().items():
                if layer_name not in geoms.keys():
                    geoms[layer_name] = []
                geoms[layer_name].extend(layer_geoms)
        return geoms

    def get_flat_transform(self, maxdepth=None):
        return pc.Transform()

    def final(self):
        return self

    def depth(self):
        return 0

    def descend(self):
        yield self

    def descend_p(self):
        return
        yield

    def proxy(self):
        return pc.Proxy(self)

    def copy(*args, **kwargs):
        """
        Don't copy components, copy proxies
        """
        return NotImplemented

    def walk_hier(self):
        yield self
        for subcompo in self.subcompos.values():
            yield from subcompo.walk_hier()

    # Transform functions #
    # TODO for all transforms
    #def scale(self, factor):
    #    return pc.Proxy(
    #        self,
    #        transform=pc.Transform().scale(factor)
    #        )

    #def movex(self, factor):
    #    return pc.Proxy(
    #        self,
    #        transform=pc.Transform().movex(factor)
    #        )

    #def movey(self, factor):
    #    return pc.Proxy(
    #        self,
    #        transform=pc.Transform().movey(factor)
    #        )

    #def rotate(self, angle):
    #    return pc.Proxy(
    #        self,
    #        transform=pc.Transform().rotate(angle)
    #        )

    # lmap function #
    def __matmul__(self, what):
        if isinstance(what, dict | str):  # TODO lmap shorthand type
            return pc.Proxy(
                self,
                lmap=what
                )
        elif isinstance(what, pc.Transform):
            return pc.Proxy(
                self,
                transform=what
                )
        else:
            raise Exception()  # TODO

    # mark functions #
    def set_mark(self, name, point):
        # TODO this is a boundpoint but not actually a boundpoint?
        self.marks[name] = pc.BoundPoint(point, None)

    def get_mark(self, name):
        return self.marks[name]

    # bbox functions #
    @property
    def bbox(self):
        bbox = pc.BBox()
        for geoms in self.get_geoms().values():
            for geom in geoms:
                bbox.add_xyarray(geom)
        return bbox

    def __init_subclass__(cls):
        _class_to_dictlist(cls, 'Marks', pc.Mark)
        _class_to_dictlist(cls, 'Layers', pc.Layer)
        _class_to_dictlist(cls, 'Options', pc.Option)

        for param in inspect.signature(cls._make).parameters.values():
            if param.name not in cls.Options.keys():
                # TODO unannotated
                continue

            cls.Options[param.name].annot = pc.Empty
            cls.Options[param.name].default = pc.Empty

            if param.default is not inspect._empty:
                cls.Options[param.name].default = param.default

            if param.annotation is inspect._empty:
                if param.default is not inspect._empty:
                    cls.Options[param.name].annot = type(param.default)
            else:
                cls.Options[param.name].annot = param.annotation

    # Condemned method, I don't like it
    #def subcompo(self, compo, name: str | None = None):
    #    proxy = pc.Proxy(compo)
    #    if name is None:
    #        self.subcompos.append(proxy)
    #    else:
    #        # TODO runtime check for subcompo reassignment?
    #        self.subcompos[name] = proxy
    #    return proxy

    def auto_subcompos(self, locs=None):
        """
        Automatically add all proxies defined in whatever function you
        call this from as subcompos using some arcane stack inspection
        hackery.
        """
        # Get all local variables in the above frame
        locs = locs or inspect.stack()[1].frame.f_locals

        for name, obj in locs.items():
            if (
                    isinstance(obj, pc.Proxy)
                    and name != 'self'
                    and not name.startswith('_')
                    ):
                # TODO forbid adding compo directly as subcompo,
                # only proxy, instead of doing it automatically.
                self.subcompos[name] = obj

    def _export_cif(self, transform=None):
        return NotImplemented

    def __str__(self):
        return (
            "<"
            f"{type(self).__name__} at {pc.wingdingify(id(self))} "
            ">"
            )

    def __repr__(self):
        return self.__str__()

    def _repr_svg_(self):
        """
        Make svg representation of component.
        This is called by jupyter and raimad doc
        """
        return pc.export_svg(self)

def _class_to_dictlist(cls, attr, wanted_type):
    if not hasattr(cls, attr):
        setattr(cls, attr, pc.DictList())
        return

    new_list = pc.DictList()
    for name, annot in getattr(cls, attr).__dict__.items():
        if not isinstance(annot, wanted_type):
            continue
        annot.name = name
        new_list[name] = annot

    setattr(cls, attr, new_list)

