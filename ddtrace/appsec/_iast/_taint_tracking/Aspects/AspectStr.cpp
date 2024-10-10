#include <Aspects/AspectStr.h>
#include <Aspects/Helpers.h>

static void
set_lengthupdated_ranges(PyObject* result,
                         Py_ssize_t result_len,
                         const TaintRangeRefs& ranges,
                         const TaintRangeMapTypePtr& tx_map)
{
    if (!tx_map || tx_map->empty()) {
        return;
    }

    TaintRangeRefs copy_ranges(ranges);
    for (auto& range : copy_ranges) {
        range->length = result_len;
    }

    set_ranges(result, copy_ranges, tx_map);
}

static PyObject*
call_original_function(PyObject* orig_function, PyObject* text, PyObject* pyo_encoding, PyObject* pyo_errors)
{
    PyObject* arg_errors = pyo_errors ? pyo_errors : PyUnicode_FromString("strict");
    const auto res = PyObject_CallFunction(orig_function, "OOO", text, pyo_encoding, arg_errors);
    if (res == nullptr) {
        return nullptr;
    }
    return res;
}

static std::tuple<int, PyObject*, PyObject*, PyObject*, PyObject*>
get_args(PyObject* const* args, const Py_ssize_t nargs, PyObject* kwnames)
{
    PyObject* orig_function = args[0];
    PyObject* text = args[2];
    PyObject* pyo_encoding = nullptr;
    PyObject* pyo_errors = nullptr;
    int effective_args = 1;

    if (nargs > 3) {
        pyo_encoding = args[3];
        effective_args = 2;
    }
    if (nargs > 4) {
        pyo_errors = args[4];
        effective_args = 3;
    }

    if (kwnames and PyTuple_Check(kwnames)) {
        for (Py_ssize_t i = 0; i < PyTuple_Size(kwnames); i++) {
            if (effective_args > 3) {
                // Will produce an error, so end here
                break;
            }
            PyObject* key = PyTuple_GET_ITEM(kwnames, i); // Keyword name
            PyObject* value = args[nargs + i];            // Keyword value
            if (PyUnicode_CompareWithASCIIString(key, "encoding") == 0) {
                pyo_encoding = value;
                ++effective_args;
                continue;
            }
            if (PyUnicode_CompareWithASCIIString(key, "errors") == 0) {
                ++effective_args;
                pyo_errors = value;
            }
        }
    }

    return { effective_args, orig_function, text, pyo_encoding, pyo_errors };
}

PyObject*
api_str_aspect(PyObject* self, PyObject* const* args, const Py_ssize_t nargs, PyObject* kwnames)
{
    if (nargs < 3 or nargs > 5) {
        py::set_error(PyExc_ValueError, MSG_ERROR_N_PARAMS);
        return nullptr;
    }

    auto [effective_args, orig_function, text, pyo_encoding, pyo_errors] = get_args(args, nargs, kwnames);

    if (effective_args > 3) {
        string error_msg = "str() takes at most 3 arguments (" + to_string(effective_args) + " given)";
        py::set_error(PyExc_TypeError, error_msg.c_str());
        return nullptr;
    }

    const bool has_encoding = pyo_encoding != nullptr and PyUnicode_GetLength(pyo_encoding) > 0;
    const bool has_errors = pyo_errors != nullptr and PyUnicode_GetLength(pyo_errors) > 0;

    // If it has encoding, then the text object must be a bytes or bytearray object; if not, call the original
    // function so the error is raised
    if (has_encoding and (not PyByteArray_Check(text) and not PyBytes_Check(text))) {
        return call_original_function(orig_function, text, pyo_encoding, pyo_errors);
    }

    // Call the original if not a text type and has no encoding
    if (not is_text(text)) {
        PyObject* as_str = PyObject_Str(text);
        return as_str;
    }

    PyObject* result_o = nullptr;

    // With no encoding or errors arguments we can directly call PyObject_Str, which is faster
    if (!has_encoding and !has_errors) {
        result_o = PyObject_Str(text);
        if (result_o == nullptr) {
            return nullptr;
        }
    } else {
        // Oddly enough, the presence of just the "errors" argument is enough to trigger the decoding
        // behaviour of str() even is "encoding" is empty (but then it will take the default utf-8 value)
        char* text_raw_bytes = nullptr;
        Py_ssize_t text_raw_bytes_size;

        if (PyByteArray_Check(text)) {
            text_raw_bytes = PyByteArray_AS_STRING(text);
            text_raw_bytes_size = PyByteArray_GET_SIZE(text);
        } else if (PyBytes_AsStringAndSize(text, &text_raw_bytes, &text_raw_bytes_size) == -1) {
            if (has_pyerr()) {
                return nullptr;
            }
            throw py::error_already_set();
        }

        const char* encoding = has_encoding ? PyUnicode_AsUTF8(pyo_encoding) : "utf-8";
        const char* errors = has_errors ? PyUnicode_AsUTF8(pyo_errors) : "strict";
        result_o = PyUnicode_Decode(text_raw_bytes, text_raw_bytes_size, encoding, errors);

        if (PyErr_Occurred()) {
            return nullptr;
        }
        if (result_o == nullptr) {
            Py_RETURN_NONE;
        }
    }

    TRY_CATCH_ASPECT("str_aspect", return result_o, , {
        const auto tx_map = Initializer::get_tainting_map();
        if (!tx_map || tx_map->empty()) {
            return result_o;
        }

        auto [ranges, ranges_error] = get_ranges(text, tx_map);
        if (ranges_error || ranges.empty()) {
            return result_o;
        }

        if (PyUnicode_Check(text)) {
            set_ranges(result_o, ranges, tx_map);
        } else {
            // Encoding on Bytes or Bytearray: size could change
            const auto len_result_o = PyObject_Length(result_o);
            PyObject* check_offset = PyObject_Str(text);

            if (check_offset == nullptr) {
                PyErr_Clear();
                set_lengthupdated_ranges(result_o, len_result_o, ranges, tx_map);
            } else {
                Py_ssize_t offset = PyUnicode_Find(result_o, check_offset, 0, len_result_o, 1);
                if (offset == -1) {
                    PyErr_Clear();
                    set_lengthupdated_ranges(result_o, len_result_o, ranges, tx_map);
                } else {
                    copy_and_shift_ranges_from_strings(text, result_o, offset, len_result_o, tx_map);
                }
            }
            Py_DECREF(check_offset);
        }
        return result_o;
    });
}
