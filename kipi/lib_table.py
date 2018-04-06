

def read_fp_lib_table(filename):
    return read_lib_table (filename, "fp")

def read_sym_lib_table(filename):
    return read_lib_table (filename, "sym")

def read_lib_table(filename, atype):
    fr = open(filename, "r")
    d = fr.read()
    fr.close()

    table_tag = "(" + atype + "_lib_table"

    d = d[d.find(table_tag) + len(table_tag):]

    d = d.strip()
    libs = []
    while d.find("(lib") > -1:
        d = d[d.find("(lib") + 4:].strip()

        lib = {}
        while True:
            tok, d = d.split(")", 1)
            if tok == "":
                break

            tok = tok.strip("(")
            tokens = tok.split(None, 1)

            key = tokens[0]
            if len(tokens)>1 :
                val = tokens[1]
            else:
                val = None
            lib[key] = val

        libs.append(lib)

    return libs

def write_fp_lib_table(filename, libs):
    write_lib_table (filename, "fp", libs)

def write_sym_lib_table(filename, libs):
    write_lib_table (filename, "sym", libs)

def write_lib_table(filename, atype, libs):
    fw = open(filename, "w")

    if atype == "fp":
        fw.write("(fp_lib_table\n")
    else:
        fw.write("(sym_lib_table\n")

    for lib in libs:
        line = "(lib (name %s)(type %s)(uri %s)(options %s)(descr %s)" % (lib['name'], lib['type'], lib['uri'], lib['options'], lib['descr'])
        if 'disabled' in lib:
            line += "(disabled)"
        line += ")"
        fw.write("  %s\n" % line)

    fw.write(")\n")
    fw.close()

