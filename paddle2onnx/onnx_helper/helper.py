#   Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Copyright (c) ONNX Project Contributors.
# Licensed under the MIT license.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import collections
import numbers
from six import text_type, integer_types, binary_type

import google.protobuf.message
from .onnx_pb import TensorProto, SparseTensorProto, AttributeProto, ValueInfoProto, TensorShapeProto, \
    NodeProto, ModelProto, GraphProto, OperatorSetIdProto, TypeProto, IR_VERSION
from paddle2onnx.onnx_helper import mapping
from .mapping import STORAGE_TENSOR_TYPE_TO_FIELD
import numpy as np  # type: ignore


def make_node(
        op_type,  # type: Text
        inputs,  # type: Sequence[Text]
        outputs,  # type: Sequence[Text]
        name=None,  # type: Optional[Text]
        doc_string=None,  # type: Optional[Text]
        domain=None,  # type: Optional[Text]
        **kwargs  # type: Any
):  # type: (...) -> NodeProto
    """Construct a NodeProto.

    Arguments:
        op_type (string): The name of the operator to construct
        inputs (list of string): list of input names
        outputs (list of string): list of output names
        name (string, default None): optional unique identifier for NodeProto
        doc_string (string, default None): optional documentation string for NodeProto
        domain (string, default None): optional domain for NodeProto.
            If it's None, we will just use default domain (which is empty)
        **kwargs (dict): the attributes of the node.  The acceptable values
            are documented in :func:`make_attribute`.
    """

    node = NodeProto()
    node.op_type = op_type
    node.input.extend(inputs)
    node.output.extend(outputs)
    if name:
        node.name = name
    if doc_string:
        node.doc_string = doc_string
    if domain is not None:
        node.domain = domain
    if kwargs:
        node.attribute.extend(
            make_attribute(key, value) for key, value in sorted(kwargs.items()))
    return node


def make_operatorsetid(
        domain,  # type: Text
        version,  # type: int
):  # type: (...) -> OperatorSetIdProto
    """Construct an OperatorSetIdProto.

    Arguments:
        domain (string): The domain of the operator set id
        version (integer): Version of operator set id
    """
    operatorsetid = OperatorSetIdProto()
    operatorsetid.domain = domain
    operatorsetid.version = version
    return operatorsetid


def make_graph(
        nodes,  # type: Sequence[NodeProto]
        name,  # type: Text
        inputs,  # type: Sequence[ValueInfoProto]
        outputs,  # type: Sequence[ValueInfoProto]
        initializer=None,  # type: Optional[Sequence[TensorProto]]
        doc_string=None,  # type: Optional[Text]
        value_info=[],  # type: Sequence[ValueInfoProto]
):  # type: (...) -> GraphProto
    if initializer is None:
        initializer = []
    if value_info is None:
        value_info = []
    graph = GraphProto()
    graph.node.extend(nodes)
    graph.name = name
    graph.input.extend(inputs)
    graph.output.extend(outputs)
    graph.initializer.extend(initializer)
    graph.value_info.extend(value_info)
    if doc_string:
        graph.doc_string = doc_string
    return graph


def make_opsetid(domain, version):  # type: (Text, int) -> OperatorSetIdProto
    opsetid = OperatorSetIdProto()
    opsetid.domain = domain
    opsetid.version = version
    return opsetid


def make_model(graph, **kwargs):  # type: (GraphProto, **Any) -> ModelProto
    model = ModelProto()
    # Touch model.ir_version so it is stored as the version from which it is
    # generated.
    model.ir_version = IR_VERSION
    model.graph.CopyFrom(graph)

    opset_imports = None  # type: Optional[Sequence[OperatorSetIdProto]]
    opset_imports = kwargs.pop('opset_imports', None)  # type: ignore
    if opset_imports is not None:
        model.opset_import.extend(opset_imports)
    else:
        # Default import
        imp = model.opset_import.add()
        #imp.version = defs.onnx_opset_version()

    for k, v in kwargs.items():
        # TODO: Does this work with repeated fields?
        setattr(model, k, v)
    return model


def set_model_props(model,
                    dict_value):  # type: (ModelProto, Dict[Text, Text]) -> None
    del model.metadata_props[:]
    for (k, v) in dict_value.items():
        entry = model.metadata_props.add()
        entry.key = k
        entry.value = v
        # model.metadata_properties.append(entry)


def split_complex_to_pairs(
        ca):  # type: (Sequence[np.complex64]) -> Sequence[int]
    return [(ca[i // 2].real if (i % 2 == 0) else ca[i // 2].imag)
            for i in range(len(ca) * 2)]


def make_tensor(
        name,  # type: Text
        data_type,  # type: int
        dims,  # type: Sequence[int]
        vals,  # type: Any
        raw=False  # type: bool
):  # type: (...) -> TensorProto
    '''
    Make a TensorProto with specified arguments.  If raw is False, this
    function will choose the corresponding proto field to store the
    values based on data_type. If raw is True, use "raw_data" proto
    field to store the values, and values should be of type bytes in
    this case.
    '''
    tensor = TensorProto()
    tensor.data_type = data_type
    tensor.name = name

    if data_type == TensorProto.STRING:
        assert not raw, "Can not use raw_data to store string type"

    if (data_type == TensorProto.COMPLEX64 or
            data_type == TensorProto.COMPLEX128):
        vals = split_complex_to_pairs(vals)
    if raw:
        tensor.raw_data = vals
    else:
        field = mapping.STORAGE_TENSOR_TYPE_TO_FIELD[
            mapping.TENSOR_TYPE_TO_STORAGE_TENSOR_TYPE[data_type]]
        getattr(tensor, field).extend(vals)

    tensor.dims.extend(dims)
    return tensor


def make_sparse_tensor(
        values,  # type: TensorProto
        indices,  # type: TensorProto
        dims  # type: Sequence[int]
):  # type: (...) -> SparseTensorProto
    sparse = SparseTensorProto()
    sparse.values.CopyFrom(values)
    sparse.indices.CopyFrom(indices)
    sparse.dims.extend(dims)
    return sparse


def _to_bytes_or_false(val):  # type: (Union[Text, bytes]) -> Union[bytes, bool]
    """An internal graph to convert the input to a bytes or to False.

    The criteria for conversion is as follows and should be python 2 and 3
    compatible:
    - If val is py2 str or py3 bytes: return bytes
    - If val is py2 unicode or py3 str: return val.decode('utf-8')
    - Otherwise, return False
    """
    if isinstance(val, bytes):
        return val
    try:
        return val.encode('utf-8')
    except AttributeError:
        return False


def make_attribute(
        key,  # type: Text
        value,  # type: Any
        doc_string=None  # type: Optional[Text]
):  # type: (...) -> AttributeProto
    """Makes an AttributeProto based on the value type."""
    attr = AttributeProto()
    attr.name = key
    if doc_string:
        attr.doc_string = doc_string

    is_iterable = isinstance(value, collections.Iterable)
    bytes_or_false = _to_bytes_or_false(value)
    # First, singular cases
    # float
    if isinstance(value, float):
        attr.f = value
        attr.type = AttributeProto.FLOAT
    # integer
    elif isinstance(value, numbers.Integral):
        attr.i = value
        attr.type = AttributeProto.INT
    # string
    elif bytes_or_false is not False:
        assert isinstance(bytes_or_false, bytes)
        attr.s = bytes_or_false
        attr.type = AttributeProto.STRING
    elif isinstance(value, TensorProto):
        attr.t.CopyFrom(value)
        attr.type = AttributeProto.TENSOR
    elif isinstance(value, SparseTensorProto):
        attr.sparse_tensor.CopyFrom(value)
        attr.type = AttributeProto.SPARSE_TENSOR
    elif isinstance(value, GraphProto):
        attr.g.CopyFrom(value)
        attr.type = AttributeProto.GRAPH
    # third, iterable cases
    elif is_iterable:
        byte_array = [_to_bytes_or_false(v) for v in value]
        if all(isinstance(v, float) for v in value):
            attr.floats.extend(value)
            attr.type = AttributeProto.FLOATS
        elif all(isinstance(v, numbers.Integral) for v in value):
            # Turn np.int32/64 into Python built-in int.
            attr.ints.extend(int(v) for v in value)
            attr.type = AttributeProto.INTS
        elif all(
                map(lambda bytes_or_false: bytes_or_false is not False,
                    byte_array)):
            attr.strings.extend(byte_array)
            attr.type = AttributeProto.STRINGS
        elif all(isinstance(v, TensorProto) for v in value):
            attr.tensors.extend(value)
            attr.type = AttributeProto.TENSORS
        elif all(isinstance(v, SparseTensorProto) for v in value):
            attr.sparse_tensors.extend(value)
            attr.type = AttributeProto.SPARSE_TENSORS
        elif all(isinstance(v, GraphProto) for v in value):
            attr.graphs.extend(value)
            attr.type = AttributeProto.GRAPHS
        else:
            raise ValueError(
                "You passed in an iterable attribute but I cannot figure out "
                "its applicable type.")
    else:
        raise TypeError('value "{}" is not valid attribute data type.'.format(
            value))
    return attr


def get_attribute_value(attr):  # type: (AttributeProto) -> Any
    if attr.type == AttributeProto.FLOAT:
        return attr.f
    if attr.type == AttributeProto.INT:
        return attr.i
    if attr.type == AttributeProto.STRING:
        return attr.s
    if attr.type == AttributeProto.TENSOR:
        return attr.t
    if attr.type == AttributeProto.GRAPH:
        return attr.g
    if attr.type == AttributeProto.FLOATS:
        return list(attr.floats)
    if attr.type == AttributeProto.INTS:
        return list(attr.ints)
    if attr.type == AttributeProto.STRINGS:
        return list(attr.strings)
    if attr.type == AttributeProto.TENSORS:
        return list(attr.tensors)
    if attr.type == AttributeProto.GRAPHS:
        return list(attr.graphs)
    raise ValueError("Unsupported ONNX attribute: {}".format(attr))


def make_empty_tensor_value_info(name):  # type: (Text) -> ValueInfoProto
    value_info_proto = ValueInfoProto()
    value_info_proto.name = name
    return value_info_proto


def make_tensor_value_info(
        name,  # type: Text
        elem_type,  # type: int
        shape,  # type: Optional[Sequence[Union[Text, int]]]
        doc_string="",  # type: Text
        shape_denotation=None,  # type: Optional[List[Text]]
):  # type: (...) -> ValueInfoProto
    """Makes a ValueInfoProto based on the data type and shape."""
    value_info_proto = ValueInfoProto()
    value_info_proto.name = name
    if doc_string:
        value_info_proto.doc_string = doc_string

    tensor_type_proto = value_info_proto.type.tensor_type
    tensor_type_proto.elem_type = elem_type

    tensor_shape_proto = tensor_type_proto.shape

    if shape is not None:
        # You might think this is a no-op (extending a normal Python
        # list by [] certainly is), but protobuf lists work a little
        # differently; if a field is never set, it is omitted from the
        # resulting protobuf; a list that is explicitly set to be
        # empty will get an (empty) entry in the protobuf. This
        # difference is visible to our consumers, so make sure we emit
        # an empty shape!
        tensor_shape_proto.dim.extend([])

        if shape_denotation:
            if len(shape_denotation) != len(shape):
                raise ValueError('Invalid shape_denotation. '
                                 'Must be of the same length as shape.')

        for i, d in enumerate(shape):
            dim = tensor_shape_proto.dim.add()
            if d is None:
                pass
            elif isinstance(d, integer_types):
                dim.dim_value = d
            elif isinstance(d, text_type):
                dim.dim_param = d
            else:
                raise ValueError(
                    'Invalid item in shape: {}. '
                    'Needs to of integer_types or text_type.'.format(d))

            if shape_denotation:
                dim.denotation = shape_denotation[i]

    return value_info_proto


def make_sequence_value_info(
        name,  # type: Text
        elem_type,  # type: int
        shape,  # type: Optional[Sequence[Union[Text, int]]]
        doc_string="",  # type: Text
        elem_shape_denotation=None,  # type: Optional[List[Text]]
):  # type: (...) -> ValueInfoProto
    """Makes a ValueInfoProto based on the data type and shape for Sequence."""
    value_info_proto = ValueInfoProto()
    value_info_proto.name = name
    if doc_string:
        value_info_proto.doc_string = doc_string

    sequence_type_proto = value_info_proto.type.sequence_type
    sequence_type_proto.elem_type.tensor_type.elem_type = elem_type

    tensor_value_info = make_tensor_value_info(
        name, elem_type, shape, doc_string, elem_shape_denotation)

    if shape is not None:
        sequence_type_proto.elem_type.tensor_type.shape.CopyFrom(
            tensor_value_info.type.tensor_type.shape)

    return value_info_proto


def _sanitize_str(s):  # type: (Union[Text, bytes]) -> Text
    if isinstance(s, text_type):
        sanitized = s
    elif isinstance(s, binary_type):
        sanitized = s.decode('utf-8', errors='ignore')
    else:
        sanitized = str(s)
    if len(sanitized) < 64:
        return sanitized
    return sanitized[:64] + '...<+len=%d>' % (len(sanitized) - 64)


def printable_attribute(
        attr, subgraphs=False
):  # type: (AttributeProto, bool) -> Union[Text, Tuple[Text, List[GraphProto]]]
    content = []
    content.append(attr.name)
    content.append("=")

    def str_float(f):  # type: (float) -> Text
        # NB: Different Python versions print different numbers of trailing
        # decimals, specifying this explicitly keeps it consistent for all
        # versions
        return '{:.15g}'.format(f)

    def str_int(i):  # type: (int) -> Text
        # NB: In Python 2, longs will repr() as '2L', which is ugly and
        # unnecessary.  Explicitly format it to keep it consistent.
        return '{:d}'.format(i)

    def str_str(s):  # type: (Text) -> Text
        return repr(s)

    #_T = TypeVar('_T')  # noqa

    def str_list(str_elem,
                 xs):  # type: (Callable[[_T], Text], Sequence[_T]) -> Text
        return '[' + ', '.join(map(str_elem, xs)) + ']'

    # for now, this logic should continue to work as long as we are running on a proto3
    # implementation. If/when we switch to proto3, we will need to use attr.type

    # To support printing subgraphs, if we find a graph attribute, print out
    # its name here and pass the graph itself up to the caller for later
    # printing.
    graphs = []
    if attr.HasField("f"):
        content.append(str_float(attr.f))
    elif attr.HasField("i"):
        content.append(str_int(attr.i))
    elif attr.HasField("s"):
        # TODO: Bit nervous about Python 2 / Python 3 determinism implications
        content.append(repr(_sanitize_str(attr.s)))
    elif attr.HasField("t"):
        if len(attr.t.dims) > 0:
            content.append("<Tensor>")
        else:
            # special case to print scalars
            field = STORAGE_TENSOR_TYPE_TO_FIELD[attr.t.data_type]
            content.append('<Scalar Tensor {}>'.format(
                str(getattr(attr.t, field))))
    elif attr.HasField("g"):
        content.append("<graph {}>".format(attr.g.name))
        graphs.append(attr.g)
    elif attr.floats:
        content.append(str_list(str_float, attr.floats))
    elif attr.ints:
        content.append(str_list(str_int, attr.ints))
    elif attr.strings:
        # TODO: Bit nervous about Python 2 / Python 3 determinism implications
        content.append(str(list(map(_sanitize_str, attr.strings))))
    elif attr.tensors:
        content.append("[<Tensor>, ...]")
    elif attr.graphs:
        content.append('[')
        for i, g in enumerate(attr.graphs):
            comma = ',' if i != len(attr.graphs) - 1 else ''
            content.append('<graph {}>{}'.format(g.name, comma))
        content.append(']')
        graphs.extend(attr.graphs)
    else:
        content.append("<Unknown>")
    if subgraphs:
        return ' '.join(content), graphs
    else:
        return ' '.join(content)


def printable_dim(dim):  # type: (TensorShapeProto.Dimension) -> Text
    which = dim.WhichOneof('value')
    assert which is not None
    return str(getattr(dim, which))


def printable_type(t):  # type: (TypeProto) -> Text
    if t.WhichOneof('value') == "tensor_type":
        s = TensorProto.DataType.Name(t.tensor_type.elem_type)
        if t.tensor_type.HasField('shape'):
            if len(t.tensor_type.shape.dim):
                s += str(', ' + 'x'.join(
                    map(printable_dim, t.tensor_type.shape.dim)))
            else:
                s += str(', scalar')
        return s
    if t.WhichOneof('value') is None:
        return ""
    return 'Unknown type {}'.format(t.WhichOneof('value'))


def printable_value_info(v):  # type: (ValueInfoProto) -> Text
    s = '%{}'.format(v.name)
    if v.type:
        s = '{}[{}]'.format(s, printable_type(v.type))
    return s


def printable_tensor_proto(t):  # type: (TensorProto) -> Text
    s = '%{}['.format(t.name)
    s += TensorProto.DataType.Name(t.data_type)
    if t.dims is not None:
        if len(t.dims):
            s += str(', ' + 'x'.join(map(str, t.dims)))
        else:
            s += str(', scalar')
    s += ']'
    return s


def printable_node(
        node, prefix='', subgraphs=False
):  # type: (NodeProto, Text, bool) -> Union[Text, Tuple[Text, List[GraphProto]]]
    content = []
    if len(node.output):
        content.append(', '.join(['%{}'.format(name) for name in node.output]))
        content.append('=')
    # To deal with nested graphs
    graphs = []  # type: List[GraphProto]
    printed_attrs = []
    for attr in node.attribute:
        if subgraphs:
            printed_attr, gs = printable_attribute(attr, subgraphs)
            assert isinstance(gs, list)
            graphs.extend(gs)
            printed_attrs.append(printed_attr)
        else:
            printed = printable_attribute(attr)
            assert isinstance(printed, Text)
            printed_attrs.append(printed)
    printed_attributes = ', '.join(sorted(printed_attrs))
    printed_inputs = ', '.join(['%{}'.format(name) for name in node.input])
    if node.attribute:
        content.append("{}[{}]({})".format(node.op_type, printed_attributes,
                                           printed_inputs))
    else:
        content.append("{}({})".format(node.op_type, printed_inputs))
    if subgraphs:
        return prefix + ' '.join(content), graphs
    else:
        return prefix + ' '.join(content)


def printable_graph(graph, prefix=''):  # type: (GraphProto, Text) -> Text
    content = []
    indent = prefix + '  '
    # header
    header = ['graph', graph.name]
    initializers = {t.name for t in graph.initializer}
    if len(graph.input):
        header.append("(")
        in_strs = []  # required inputs
        in_with_init_strs = [
        ]  # optional inputs with initializer providing default value
        for inp in graph.input:
            if inp.name not in initializers:
                in_strs.append(printable_value_info(inp))
            else:
                in_with_init_strs.append(printable_value_info(inp))
        if in_strs:
            content.append(prefix + ' '.join(header))
            header = []
            for line in in_strs:
                content.append(prefix + '  ' + line)
        header.append(")")

        if in_with_init_strs:
            header.append("optional inputs with matching initializers (")
            content.append(prefix + ' '.join(header))
            header = []
            for line in in_with_init_strs:
                content.append(prefix + '  ' + line)
            header.append(")")

        # from IR 4 onwards an initializer is not required to have a matching graph input
        # so output the name, type and shape of those as well
        if len(in_with_init_strs) < len(initializers):
            graph_inputs = {i.name for i in graph.input}
            init_strs = [
                printable_tensor_proto(i) for i in graph.initializer
                if i.name not in graph_inputs
            ]
            header.append("initializers (")
            content.append(prefix + ' '.join(header))
            header = []
            for line in init_strs:
                content.append(prefix + '  ' + line)
            header.append(")")

    header.append('{')
    content.append(prefix + ' '.join(header))
    graphs = []  # type: List[GraphProto]
    # body
    for node in graph.node:
        pn, gs = printable_node(node, indent, subgraphs=True)
        assert isinstance(gs, list)
        content.append(pn)
        graphs.extend(gs)
    # tail
    tail = ['return']
    if len(graph.output):
        tail.append(', '.join(['%{}'.format(out.name) for out in graph.output]))
    content.append(indent + ' '.join(tail))
    # closing bracket
    content.append(prefix + '}')
    for g in graphs:
        content.append('\n' + printable_graph(g))
    return '\n'.join(content)


def strip_doc_string(proto):  # type: (google.protobuf.message.Message) -> None
    """
    Empties `doc_string` field on any nested protobuf messages
    """
    assert isinstance(proto, google.protobuf.message.Message)
    for descriptor in proto.DESCRIPTOR.fields:
        if descriptor.name == 'doc_string':
            proto.ClearField(descriptor.name)
        elif descriptor.type == descriptor.TYPE_MESSAGE:
            if descriptor.label == descriptor.LABEL_REPEATED:
                for x in getattr(proto, descriptor.name):
                    strip_doc_string(x)
            elif proto.HasField(descriptor.name):
                strip_doc_string(getattr(proto, descriptor.name))
