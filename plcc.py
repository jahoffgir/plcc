# -*-python-*-

import sys
import re
import os
import shutil

argv = sys.argv[1:] # skip over the command-line argument

# current file information
Lno = 0             # current line number
Fname = ''          # current file name (STDIN if standard input)
Line = ''           # current line in the file
STD = []            # reserved names from Std library classes
STDT = []           # token-related files in the Std library directory
STDP = []           # parse-related files in the Std library directory

flags = {}          # processing flags (dictionary)

startSymbol = ''    # start symbol (first nonterm in rules)
skip = set()        # set of skip names
term = set()        # set of term (token) names
skipSpecs = []      # skip specifications for generating the Token file
termSpecs = []      # term (token) specifications for generating the Token file

nonterms = set()    # set of all nonterms
fields = {}         # maps a non-abstract class name to its list of fields
rules = []          # list of items  of the form (nt, cls, rhs), one for each grammar rule
extends = {}        # maps a derived class to its abstract base class
derives = {}        # maps an abstract class to a list of its derived classes
cases = {}          # maps a non-abstract class to its set of case terminals for use in a switch
arbno = {}          # maps an arbno class name to its separator string (or None)
stubs = {}          # maps a class name to its parser stub file


def debug(msg, level=1):
    # print(getFlag('debug'))
    if msg and getFlag('debug') >= level:
        print(">>>", msg, file=sys.stderr)
        return True
    return False

def debug2(msg):
    debug(msg, level=2)

def LIBPLCC():
    try:
        return os.environ['LIBPLCC']
    except KeyError:
        return '/usr/local/pub/tvf/PLCC' ######## System specific! ########

def main():
    global argv
    plccInit()
    while argv:
        if argv[0] == '--':
            # just continue with the rest of the command line
            argv = argv[1:]
            break
        (flag, ee, val) = argv[0].partition("=")
        # print('flag=%s val=%s' % (flag, val))
        flag = flag.strip()
        if  flag[:2] == '--':
            key = flag[2:].strip()
            if key == '':
                # no key
                death('illegal command line parameter')
            val = val.strip()
            if ee:
                # map key to val, using processFlag
                try:
                    processFlag('%s=%s' % (key, val))
                except Exception as msg:
                    death(msg)
            else:
                processFlag(key)
            argv = argv[1:]
        else:
            break
    nxt = nextLine()     # nxt is the next line generator
    lex(nxt)    # lexical analyzer generation
    par(nxt)    # LL(1) check and parser generation
    sem(nxt)    # semantic actions

def plccInit():
    global flags, STD, STDT, STDP
    STDT = ['ILazy','IMatch','ITrace','IScan','Trace','Scan']
    STDP = ['Parser','Rep']
    STD = STDT + STDP
    STD.append('Token')
    # file-related flags -- can be overwritten
    # by a grammar file '!flag=...' spec
    # or by a '--flag=...' command line argument
    for fname in STD:
        flags[fname] = fname
    flags['libplcc'] = LIBPLCC()
    flags['Token'] = True         
    # behavior-related flags
    flags['debug'] = 0            # default debug value
    flags['destdir'] = 'Java'     # the default destination directory
    flags['pattern'] = True       # create a scanner that uses re. patterns
    flags['LL1'] = True           # check for LL(1)
    flags['parser'] = True        # create a parser
    flags['semantics'] = True     # create semantics routines
    flags['nowrite'] = False      # when True, produce *no* file output
    
def lex(nxt):
    # print('=== lexical specification')
    for line in nxt:
        if line == '%':
            break
        line = line.lstrip()
        if len(line) == 0 or line[0] == '#': # skip empty lines and comments
            continue
        line = re.sub('\s+#.*$', '', line)   # remove trailing comments ...
        line = line.rstrip()                 # ... and any remaining whitespace
        # print ('>>>', line)
        (line, n) = re.subn('^!', '', line)  # check if it's a run-time flag
        if n > 0:
            # print ('>>> flag line:', line)
            try:
                processFlag(line)
            except Exception as msg:
                deathLNO(msg)
            continue
        jpat = '' # the Java regular expression pattern for this skip/term
        pFlag = getFlag('pattern')
        if pFlag:
            # handle capturing the match part and replacing with empty string
            def qsub(match):
                nonlocal jpat
                if match:
                    jpat = match.group(1)
                    # print('match found: jpat=', jpat, sep='')
                return ''
            pat = "\s'(.*)'$"
            # print('q1 pat=', pat, sep='')
            line = re.sub(pat, qsub, line)
            if jpat:
                # add escapes to make jpat into a Java string
                jpat = re.sub(r'\\', r'\\\\', jpat)
                jpat = re.sub('"', r'\\"', jpat)
                # print('q1 match found: line=', line, ' jpat=', jpat, sep='')
                pass
            else:
                pat = '\s"(.*)"$'
                # print('q2 pat=', pat, sep='')
                line = re.sub(pat, qsub, line)
                if jpat:
                    # print('q2 match found: line=', line, ' jpat=', jpat, sep='')
                    pass
                else:
                    deathLNO('No legal pattern found!')
            jpat = '"' + jpat + '"'  # quotify
            # print('line=', line, ' jpat=', jpat, sep='')
            # make sure there are no spurious single or double quotes remaining in line
            if re.search("[\"']", line):
                deathLNO('Puzzling skip/token pattern specification')
        # next determine if it's a skip or token specification
        line = line.strip()
        result = line.split()
        rlen = len(result)
        if rlen >= 3:
            deathLNO('Illegal skip/token specification')
        if rlen == 0:
            deathLNO('No skip/token symbol')
        if rlen == 1:
            result = ['token'] + result # defaults to a token
        what = result[0]  # 'skip' or 'token'
        name = result[1]  # the term/skip name
        if what == 'skip':
            if name in skip:
                death(name + ': duplicate skip name')
            skip.update({name})
            if pFlag:
                push(skipSpecs, '%s (%s)' % (name, jpat))
            else:
                push(skipSpecs, name)
        elif what == 'token':
            if name in term:
                deathLNO('Duplicate token name: ' + name)
            term.update({name})
            if pFlag:
                push(termSpecs, '%s (%s)' % (name, jpat))
            else:
                push(termSpecs, name)
        else:
            deathLNO('No skip/token specification found')
    lexFinishUp()

def lexFinishUp():
    global skipSpecs, termSpecs, STDT
    if len(termSpecs) == 0:
        death('No tokens specified -- quitting')
    # first create the destination (Java) directory if necessary
    if getFlag('nowrite'):
        # don't write any files
        return
    dst = getFlag('destdir')
    if not dst:
        death('illegal destdir flag value')
    try:
        os.mkdir(dst)
        debug('[lexFinishUp] ' + dst + ': destination subdirectory created')
    except FileExistsError:
        debug('[lexFinishUp] ' + dst + ': destination subdirectory exists')
    except:
        death(dst + ': error creating destination subdirectory')
    if not getFlag('Token'):
        return # do not create any automatically generated scanner-related files
    libplcc = getFlag('libplcc')
    if not libplcc:
        death('illegal libplcc flag value')
    std = libplcc + '/Std'
    try:
        os.mkdir(std)
    except FileExistsError:
        pass
    except:
        death(std + ': cannot access directory') 
    fname = '%s/%s' % (dst, 'Token.java')
    try:
        tokenFile = open(fname, 'w')
    except:
        death('Cannot open ' + fname + ' for writing')
    if getFlag('pattern'):
        # use the Token.pattern library file to create Token.java
        fname = 'Token.pattern'
        try:
            tokenTemplate = open('%s/%s' % (std, fname))
        except:
            death(fname + ': cannot read library file')
        if len(skipSpecs) == 0:
            skipSpecs = ['NULL ("")']
        for line in tokenTemplate:
            # note that line keeps its trailing newline
            if re.match('^\s*%%Vals%%', line):
                tssep = ''
                for ts in termSpecs:
                    print(tssep + '        ' + ts, file=tokenFile, end='')
                    tssep = ',\n'
                print(';', file=tokenFile)
            elif re.match('^\s*%%Skips%%', line):
                sssep = ''
                for ss in skipSpecs:
                    print(sssep + '        ' + ss, file=tokenFile, end='')
                    sssep = ',\n'
                print(';', file=tokenFile)
            else:
                print(line, file=tokenFile, end='')
        tokenTemplate.close()
    else:
        # use the Token.template file to create Token.java
        fname = 'Token.template'
        try:
            tokenTemplate = open('%s/%s' % (std, fname))
        except:
            death(fname + ': cannot read library file')
        for line in tokenTemplate:
            # note that line keeps its trailing newline
            if re.match('^\s*%%Vals%%', line):
                tssep = ''
                for ts in termSpecs:
                    print(tssep + '        ' + ts, file=tokenFile, end='')
                    tssep = ',\n'
                print(';', file=tokenFile)
            else:
                print(line, file=tokenFile, end='')
        tokenTemplate.close()
    tokenFile.close()
    # copy the Std token-related library files to the destination directory
    for fname in STDT:
        if getFlag(fname):
            debug('[lexFinishUp] copying %s from %s to %s ...' % (fname, std, dst))
            try:
                shutil.copy('%s/%s.java' % (std, fname), '%s/%s.java' % (dst, fname))
            except:
                death('Failure copying %s from %s to %s' % (fname, std, dst))

def par(nxt):
    debug('[par] processing grammar rule lines')
    if not getFlag('parser'):
        done()
    rno = 0
    for line in nxt:
        if line == '%':
            break
        line = line.lstrip() # clobber leading whitespace
        line = re.sub('#.*$', '', line) # remove comments
        line = line.rstrip()            # clobber any trailing whitespace
        if line == '':
            continue                    # skip entirely blank lines
        if re.search('_', line):
            deathLNO('underscore "_" not permitted in grammar rule line')
        rno += 1
        processRule(line, rno)
    parFinishUp()

def parFinishUp():
    global STDP, startSymbol, nonterms, extends, derives, rules
    if not rules:
        done(msg='No grammar rules')
    debug('[parFinishUp] par: finishing up...')
    # check to make sure all RHS nonterms appear as the LHS of at least one rule
    for nt in nonterms:
        debug('[parFinishUp] nt=%s' % nt)
    for (nt, cls, rhs) in rules:
        rhsString = ''
        for item in rhs:
            debug('[parFinishUp] item=%s' % item)
            if isNonterm(item):
                rhsString += ' <%s>' % item
                if not item in nonterms:
                    death('nonterm %s appears on the RHS of rule "<%s> ::= %s ..." but not on any LHS' % (item, nt, rhsString))
            else:
                rhsString += ' %s' % item
        debug('[parFinishUp] rule: "<%s> ::= %s"' % (nt, rhsString))
    # if debugging, print all of the extends and derives items
    for cls in extends:
        debug('[parFinishUp] class %s extends %s' % (cls, extends[cls]))
    for base in derives:
        debug('[parFinishUp] base class %s derives %s' % (base, derives[base]))
    # print the nonterminals
    print('Nonterminals (* indicates start symbol):')
    for nt in sorted(nonterms):
        if re.search('_', nt):
            continue           # ignore automatically generated arbno names
        if nt == startSymbol:
            ss = ' *<%s>' % nt
        else:
            ss = '  <%s>' % nt
        print(ss)
    print()

    # print abstract classes
    print('Abstract classes:')
    for cls in sorted(derives):
        print('  %s' % cls)

    # check for LL1
    if getFlag('LL1'):
        checkLL1()

    if getFlag('nowrite'):
        return
    # copy the Std parser-related files 
    dst = getFlag('destdir')
    libplcc = getFlag('libplcc')
    std = libplcc + '/Std'
    for fname in STDP:
        if getFlag(fname):
            debug('[parFinishUp] copying %s from %s to %s ...' % (fname, std, dst))
            try:
                shutil.copy('%s/%s.java' % (std, fname), '%s/%s.java' % (dst, fname))
            except:
                death('Failure copying %s from %s to %s' % (fname, std, dst))
    
    # build parser stub classes
    buildStubs()
    # build the PLCC$Start.java file from the start symbol
    buildStart()

def processRule(line, rno):
    global STD, startSymbol, fields, rules, arbno, nonterm, extends, derives
    if rno:
        debug('[processRule] rule %3d: %s' % (rno, line))
    tnt = line.split()     # LHS ruleType RHS
    if len(tnt) < 2:
        deathLNO('illegal grammar rule') # no ruleType
    lhs = tnt.pop(0)       # the LHS of this rule
    nt, cls = partitionLHS(lhs)
    base = nt2cls(nt)      # turn the nonterminal name into its (base) class name
    if base in STD:
        deathLNO('%s: reserved class name' % base)
    if cls in STD:
        deathLNO('%s: reserved class name' % cls)
    if base == cls:
        deathLNO('base class and derived class names cannot be the same!')
    ruleType = tnt.pop(0)  # either '**=' or '::='
    rhs = tnt              # a list of all the items to the right of the ::= or **= on the line
    if ruleType == '**=':  # this is an arbno rule
        if cls:
            deathLNO('arbno rule cannot specify a non base class name')
        if startSymbol == '':
            deathLNO('arbno rule cannot be the first grammar rule')
        if len(rhs) == 0:
            deathLNO('arbno rules cannot be empty')
        debug('[processRule] arbno: ' + line)
        sep = rhs[-1] # get the last entry in the line
        if re.match('\+', sep):
            # must be a separated list
            sep = sep[1:] # remove the leading '+' from the separator
            if not isTerm(sep):
                deathLNO('final separator in an arbno rule must be a Terminal')
            rhs.pop()     # remove separator from the rhs list
        else:
            sep = None
        # arbno rule has no derived classes, so it's just a base class
        # saveFields(base, lhs, rhs) # check for duplicate classes; then map the base to its (lhs, rhs) pair
        arbno[base] = sep   # mark base as an arbno class with separator sep (possibly None)
        # next add non-arbno rules to the rule set to simulate arbno rules
        rhsString = ' '.join(rhs)
        ntaux = nt + '_aux'
        if sep:
            ntsep = nt + '_sep'
            processRule('<%s>      ::= %s <%s>' % (nt, rhsString, ntsep), None)
            processRule('<%s>:void ::=' % nt, None)
            processRule('<%s>:void ::= %s <%s>' % (ntaux, rhsString, ntsep), None)
            processRule('<%s>:void ::= %s <%s>' % (ntsep, sep, ntaux), None)
            processRule('<%s>:void ::=' % ntsep, None)
        else:
            processRule('<%s>      ::= %s <%s>' % (nt, rhsString, ntaux), None)
            processRule('<%s>:void ::=' % nt, None)
            processRule('<%s>:void ::= <%s>' % (ntaux, nt), None)
        return
    elif not ruleType == '::=':
        deathLNO('illegal grammar rule syntax')
    # at this point, we may have a legal non-arbno rule
    debug('[processRule] so far: %s ::= %s' % (lhs, rhs))
    nonterms.update({nt}) # add nt to the set of LHS nonterms
    if cls == 'void':
        # this rule is *generated* by an arbno rule, so there are no further class-related actions to do
        saveRule(nt, lhs, None, rhs)
        return
    if startSymbol == '':
        startSymbol = nt   # the first lhs nonterm is the start symbol
    if cls == None:
        # a simple base class -- no derived classes involved
        saveRule(nt, lhs, base, rhs)
        return
    # if we get here, cls (non-abstract) is a new class derived from base (abstract)
    if cls in derives:
        deathLNO('non-abstract class %s is already defined as an abstract class' % cls)
    if base in fields:
        deathLNO('abstract base class %s already exists as a non-abstract class' % base)
    saveRule(nt, lhs, cls, rhs)
    extends[cls] = base
    if base in derives:
        derives[base].update({cls})
    else:
        derives[base] = {cls}

# def saveFields(cls, lhs, rhs):
#     global fields
#     if cls in fields:
#         deathLNO('class %s is already defined' % cls)
#    fields[cls] = (lhs, rhs)

def saveRule(nt, lhs, cls, rhs):
    """ construct a tuple of the form (nt, tnts) where nt is the LHS nonterm (minus the <>)
        and tnts is a list of the terminal/nonterm items extracted from the rhs
        (and excluding their field names).  Then add this to the rules list for determining LL1.
        Also, map fields[cls] to the (lhs, rhs) pair
    """
    global rules, fields
    if cls != None:
        if cls in fields:
            deathLNO('class %s is already defined' % cls)
        if cls in arbno:
            fields[cls] = (lhs, rhs[:-1]) # remove the item with the underscore
        else:
            fields[cls] = (lhs, rhs)
    tnts = []
    for item in rhs:
        tnts.append(defangg(item)[0])
    rules.append((nt, cls, tnts)) # add the rule tuple to the rules list

def partitionLHS(lhs):
    # split the lhs string <xxx>[:yyy] and return xxx, yyy
    # if :yyy is missing, return xxx, None
    # xxx must be a legal nonterm name, and yyy (if present) must be either 'void' or a legal class name
    nt, c, cls = lhs.partition(':')
    if c == '':
        cls = None   # :yyy part is not present
    elif cls == '':  # :yyy is present, but yyy is empty
        deathLNO('illegal LHS: ' + lhs)
    ntt = defang(nt) # extract xxx (remove '<' and '>')
    if ntt == '':
        deathLNO('missing nonterminal')
    if ntt == 'void':
        deathLNO('cannot use "void" as a nonterminal in LHS %s' % lhs)
    if '<%s>' % ntt == nt and isNonterm(ntt):
        pass         # OK format
    else:
        deathLNO('illegal nonterminal format %s in LHS %s' %  (nt, lhs))
    if cls == None or cls == 'void' or isClass(cls):
        pass         # OK cls
    else:
        deathLNO('illegal class name %s in LHS %s' % (cls, lhs))
    return ntt, cls

def checkLL1():
    global rules, nonterms, cases
    first = {}
    follow = {}
    switch = {}

    def getFirst(form):
        nonlocal first
        # return the first set (of terminals) of this sentential form
        fst = set()
        if len(form) == 0:         # the form is empty, so it only derives Null
            return {'Null'}
        tnt = form[0]              # get the item at the start of the sentential form
        if isTerm(tnt): 
            return {tnt}           # the form starts with a terminal, which is clearly its only first set item
        # tnt must be a nonterm -- get the first set for this and add it to our current set
        f = first[tnt]             # get the current first set for tnt (=form[0])
        for t in f:
            # add all non-null stuff from first[tnt] to the current first set
            if t != 'Null':
                fst.update({t})
            else:
                # Null is in the first set for f, so recursively add the nonterms from getFirst(form[1:])
                fst.update(getFirst(form[1:]))
        # debug('first set for %s: %s' % (form, fst))
        return fst

    for nt in nonterms:
        first[nt] = set()        # initialize all of the first sets
        follow[nt] = set()       # initialize all of the follow sets
        switch[nt] = []          # maps each nonterm to a list of its first sets

    # determine the first sets
    modified = True
    while modified:
        modified = False  # assume innocent
        for (nt, cls, rhs) in rules:
            fst = first[nt]      # the current first set for this nonterminal
            fct = len(fst)       # see if the first set changes
            fst.update(getFirst(rhs))   # add any new terminals to the set
            if len(fst) != fct:
                modified = True
    if debug('[checkLL1] First sets:'):
        for nt in nonterms:
            debug('[checkLL1] %s -> %s' % (nt, first[nt]))

    # determine the follow sets
    modified = True
    while modified:
        modified = False
        for (nt, cls, rhs) in rules:
            rhs = rhs[:]         # make a copy
            debug('[checkLL1] examining rule %s ::= %s' % (nt, ' '.join(rhs)))
            while rhs:
                tnt = rhs.pop(0) # remove the first element of the list
                if isNonterm(tnt):
                    # only nonterminals count for determining follow sets
                    fol = follow[tnt]              # the current follow set for tnt
                    fct = len(fol)
                    for t in getFirst(rhs):        # look at the first set of what follows tnt (the current rhs)
                        if t == 'Null':
                            fol.update(follow[nt]) # if the rhs derives the empty string, what follows nt must follow tnt
                        else:
                            fol.update({t})        # otherwise, what the rhs derives must follow tnt
                    if len(fol) != fct:
                        modified = True
    if debug('[checkLL1] Follow sets:'):
        for nt in nonterms:
            debug('[checkLL1]   %s: %s' % (nt, ' '.join(follow[nt])))

    # determine the switch sets for each nonterm and corresponding rhs
    for (nt, cls, rhs) in rules:
        # print('### nt=%s cls=%s rhs= %s' % (nt, cls, ' '.join(rhs)))
        fst = getFirst(rhs)
        if 'Null' in fst:
            # the rhs can derive the empty string, so remove Null from the set
            fst -= {'Null'}
            # add all of the terminals in follow[nt] to this switch set
            fst.update(follow[nt])
        switch[nt].append((fst, rhs))
        if cls != None:
            saveCases(cls, fst)
    if debug('[checkLL1] nonterm switch sets:'):
        for nt in switch:
            debug('[checkLL1] %s => %s' % (nt, switch[nt]))
    
    # finally check for LL(1)
    for nt in switch:
        allTerms = set()
        for (fst, rhs) in switch[nt]:
            debug('[checkLL1] nt=%s fst=%s rhs=%s' % (nt, fst, rhs))
            s = allTerms & fst   # check to see if fst has any tokens already in allTerms
            if s:
                death('''\
not LL(1):
terms %s appear in first sets for more than one rule starting with nonterm %s
''' % (' '.join(fst), nt))
            else:
                allTerms.update(fst)
        if not allTerms:
            death('possibly useless or left-recursive grammar rule for nonterm %s' % nt)
        cases[nt] = allTerms
    pass

def saveCases(cls, fst):
    global cases, derives
    if cls in cases:
        death('cases for class %s already accounted for' % cls)
    if cls in derives:
        death('%s is an abstract class' % cls)
    # print('### class=%s cases=%s' % (cls, ' '.join(fst)))
    cases[cls] = fst

def buildStubs():
    global fields, derives, stubs
    for cls in derives:
        # make parser stubs for all abstract classes
        if cls in stubs:
            death('duplicate stub for abstract class %s' % cls)
        debug('[buildStubs] making stub for abstract class %s' % cls)
        stubs[cls] = makeAbstractStub(cls)
    for cls in fields:
        # make parser stubs for all non-abstract classes
        if cls in stubs:
            death('duplicate stub for class %s' % cls)
        debug('[buildStubs] making stub for non-abstract class %s' % cls)
        stubs[cls] = makeStub(cls)

def makeAbstractStub(base):
    global cases
    caseList = []    # a list of strings, either 'case XXX:' or '    return Cls.parse(...);'
    for cls in derives[base]:
        for tok in cases[cls]:
            caseList.append('case %s:' % tok)
        caseList.append('    return %s.parse(scn$,trace$);' % cls)
    if base == nt2cls(startSymbol):
        dummy = '\n    public %s() { } // dummy constructor\n' % base
    else:
        dummy = ''
    stubString = """\
import java.util.*;
//{base}:import//

public abstract class {base} {{
{dummy}
    public static {base} parse(Scan scn$, Trace trace$) {{
        Token t$ = scn$.cur();
        Token.Val v$ = t$.val;
        switch(v$) {{
{cases}
        default:
            throw new RuntimeException("{base} cannot begin with " + v$);
        }}
    }}

//{base}//

}}
""".format(cls=cls, base=base, dummy=dummy, cases='\n'.join(indent(2, caseList)))
    return stubString

def makeStub(cls):
    global fields, extends, arbno
    # make a stub for the given non-abstract class
    debug('[makeStub] making stub for non-abstract class %s' % cls)
    sep = False
    (lhs, rhs) = fields[cls]
    ext = '' # assume not an extended class
    # two cases: either cls is an arbno rule, or it isn't
    if cls in arbno:
        ruleType = '**='
        sep = arbno[cls]
        (fieldVars, parseString) = makeArbnoParse(cls, rhs, sep)
        if sep != None:
            rhs = rhs + ['+%s' % sep]
    else:
        ruleType = '::='
        (fieldVars, parseString) = makeParse(cls, rhs)
        # two sub-cases: either cls is an extended class (with abstract base class) or it's a base class
        if cls in extends:
            ext = ' extends ' + extends[cls]
        else:
            pass
    ruleString = '%s %s %s' % (lhs, ruleType, ' '.join(rhs))
    # fieldVars = makeVars(cls, rhs)
    decls = []
    inits = []
    params = []
    for (field, fieldType) in fieldVars:
        decls.append('public %s %s;' % (fieldType, field))
        inits.append('this.%s = %s;' % (field, field))
        params.append('%s %s' % (fieldType, field))
    debug('[makeStub] cls=%s decls=%s params=%s inits=%s' % (cls, decls, params, inits))
    debug('[makeStub] rule: %s' % ruleString)
    if cls == nt2cls(startSymbol) and params:
        dummy = '\n    public %s() { } // dummy constructor\n' % cls
    else:
        dummy = ''
    stubString = """\
import java.util.*;
//{cls}:import//

// {ruleString}
public class {cls}{ext} {{

{decls}
{dummy}
    public {cls}({params}) {{
{inits}
    }}

    public static {cls} parse(Scan scn$, Trace trace$) {{
        if (trace$ != null)
            trace$ = trace$.nonterm("{lhs}", scn$.lno);
{parse}
    }}

//{cls}//

}}
""".format(cls=cls,
           lhs=lhs,
           ext=ext,
           ruleString=ruleString,
           decls='\n'.join(indent(1, decls)),
           dummy=dummy,
           params=', '.join(params),
           inits='\n'.join(indent(2, inits)),
           parse=parseString)
    return stubString

def indent(n, iList):
    ### make a new list with the old list items prepended with 4*n spaces
    indentString = '    '*n
    newList = []
    for item in iList:
        newList.append('%s%s' % (indentString, item))
    # print('### str=%s' % str)
    return newList
    
def makeParse(cls, rhs):
    args = []
    parseList = []
    fieldVars = []
    fieldSet = set()
    for item in rhs:
        (tnt, field) = defangg(item)
        if field == None:
            parseList.append('scn$.match(Token.Val.%s, trace$);' % tnt)
            continue
        if field in fieldSet:
            death('duplicate field name %s in rule RHS %s' % (field, ' '.join(rhs)))
        fieldSet.update({field})
        args.append(field)
        if isTerm(tnt):
            fieldType = 'Token'
            parseList.append('Token %s = scn$.match(Token.Val.%s, trace$);' % (field, tnt))
        else:
            fieldType = nt2cls(tnt)
            parseList.append('%s %s = %s.parse(scn$, trace$);' % (fieldType, field, fieldType))
        fieldVars.append((field, fieldType))
    parseList.append('return new %s(%s);' % (cls, ', '.join(args)))
    debug('[makeParse] parseList=%s' % parseList)
    parseString = '\n'.join(indent(2, parseList))
    return (fieldVars, parseString)

def makeArbnoParse(cls, rhs, sep):
    # print('%%%%%% cls=%s rhs="%s" sep=%s' % (cls, ' '.join(rhs), sep))
    global cases
    inits = []       # initializes the List fields
    args = []        # the arguments to pass to the constructor
    loopList = []    # the match/parse code in the Arbno loop
    fieldVars = []   # the field variable names (all Lists), to be returned
    fieldSet = set() # the set of field variable names
    # rhs = rhs[:-1]   # remove the last item from the grammar rule (which has an underscore item)
    # create the parse statements to be included in the loop
    switchCases = [] # the token cases in the switch statement
    for item in rhs:
        (tnt, field) = defangg(item)
        if field == None:
            # a bare token -- match it
            loopList.append('scn$.match(Token.Val.%s, trace$);' % tnt)
            continue
        if field in fieldSet:
            death('duplicate field name %s in rule RHS %s' % (field, ' '.join(rhs)))
        fieldSet.update({field})
        field += 'List'
        args.append(field)
        if isTerm(tnt):
            # a term (token)
            baseType = 'Token'
            loopList.append('%s.add(scn$.match(Token.Val.%s, trace$));' % (field, tnt))
        else:
            # a nonterm
            baseType = nt2cls(tnt)
            loopList.append('%s.add(%s.parse(scn$, trace$));' % (field, baseType))
        fieldType = 'List<%s>' % baseType
        fieldVars.append((field, fieldType))
        inits.append('%s %s = new ArrayList<%s>();' % (fieldType, field, baseType))
    switchCases = []
    for item in cases[cls]:
        switchCases.append('case %s:' % item)
    returnItem = 'return new %s(%s);' % (cls, ', '.join(args))
    if sep == None:
        # no separator
        parseString = """\
{inits}
        while (true) {{
            Token t$ = scn$.cur();
            Token.Val v$ = t$.val;
            switch(v$) {{
{switchCases}
{loopList}
                continue;
            default:
                {returnItem}
            }}
        }}
""".format(inits='\n'.join(indent(2, inits)),
           switchCases='\n'.join(indent(3, switchCases)),
           loopList='\n'.join(indent(4, loopList)),
           returnItem=returnItem)
    else:
        # there's a separator
        parseString = """\
{inits}
        // first trip through the parse
        Token t$ = scn$.cur();
        Token.Val v$ = t$.val;
        switch(v$) {{
{switchCases}
            while(true) {{
{loopList}
                t$ = scn$.cur();
                v$ = t$.val;
                if (v$ != Token.Val.{sep})
                    break; // not a separator, so we're done
                scn$.match(v$, trace$);
            }}
        }} // end of switch
        {returnItem}
""".format(inits='\n'.join(indent(2, inits)),
           switchCases='\n'.join(indent(2, switchCases)),
           loopList='\n'.join(indent(4, loopList)),
           returnItem=returnItem,
           sep=sep)
    debug('[makeArbnoParse] fieldVars=%s' % fieldVars)
    return (fieldVars, parseString)

def buildStart():
    global startSymbol
    # build the PLCC$Start.java file
    if startSymbol == '':
        death('no start symbol!')
    dst = getFlag('destdir')
    if dst == None or getFlag('nowrite'):
        return
    file = 'PLCC$Start.java'
    try:
        startFile = open('%s/%s' % (dst, file), 'w')
    except:
        death('failure opening %s for writing' % file)
    startString = """\
public class PLCC$Start extends {start} {{ }}
""".format(start=nt2cls(startSymbol))
    print(startString, file=startFile)
    startFile.close()

def sem(nxt):
    global stubs, argv
    # print('=== semantic routines')
    if not getFlag('semantics'):
        semFinishUp()
        done()
    for line in nxt:
        line = line.strip()
        if line[:7] == 'include':
            # add file names to be processed
            fn = line[7:].split()
            argv.extend(fn)
            # print('== extend argv by %s' % fn)
            continue
        if line == '' or line[0] == '#':
            # skip comments or blank lines
            continue
        (cls, _, mod) = line.partition(':')
        # print('cls=%s mod=%s' % (cls, mod))
        cls = cls.strip()
        if mod:
            mod = mod.strip()
        if not isClass(cls):
            deathLNO('%s: ill-defined class name' % cls)
        codeString = getCode(nxt)
        if mod == 'ignore!':
            continue
        if cls in stubs:
            stub = stubs[cls]
            if mod:
                clsmod = '%s:%s' % (cls, mod)
            else:
                clsmod = cls
            stub = stub.replace('//%s//' % clsmod, codeString)
            debug('class %s:\n%s\n' % (cls, stub))
            stubs[cls] = stub
        else:
            if mod:
                deathLNO('no stub for class %s -- cannot replace //%s:%s//' % (cls, cls, mod))
            stubs[cls] = codeString
    semFinishUp()
    done()

def getCode(nxt):
    code = []
    for line in nxt:
        line = line.rstrip()
        if re.match(r'\s*#', line) or re.match(r'\s*$', line):
            # skip comments or blank lines
            continue
        if re.match(r'\s*%%{', line):
            stopMatch = r'\s*%%}'
            break
        if re.match(r'\s*%%%', line):
            stopMatch = r'\s*%%%'
            break
        else:
            deathLNO('expecting a code segment')
    else:
        deathLNO('premature end of file')
    for line in nxt:
        if re.match(stopMatch, line):
            break
        code.append(line)
    else:
        deathLNO('premature end of file')
    return '\n'.join(code)

def semFinishUp():
    if getFlag('nowrite'):
        return
    global stubs, STD
    dst = flags['destdir']
    print('\nJava source files created:')
    for cls in sorted(stubs):
        if cls in STD:
            death('%s: reserved class name' % cls)
        try:
            fname = '%s/%s.java' % (dst, cls)
            f = open(fname, 'w')
        except:
            death('cannot write to file %s' % fname)
        print(stubs[cls], end='', file=f)
        print('  %s.java' % cls)
        f.close()

#####################
# utility functions #
#####################

def done(msg=''):
    if msg:
        print(msg, file=sys.stderr)
    exit(0)

def nextLine():
    # create a generator to get the next line in the current input file
    global Lno, Fname, Line
    for Fname in argv:
        # open the next input file
        f = None # the current open file
        if Fname == '-':
            f = sys.stdin
            Fname = 'STDIN'
        else:
            try:
                f = open(Fname, 'r')
            except:
                death(Fname + ': error opening file')
        Lno = 0
        # f is the current open file
        for Line in f:
            # get the next line in this file
            Lno += 1
            line = Line.rstrip()
            debug('%4d [%s] %s' % (Lno,Fname,Line), level=2)
            yield line

def processFlag(flagSpec):
    global flags
    # flagSpec has been stripped
    (key,ee,val) = flagSpec.partition('=')
    key = key.rstrip()
    if re.match(r'[a-zA-Z]\w*$', key) == None:
        raise Exception('malformed flag specification: !' + flagSpec)
    val = val.lstrip()
    # '!key' makes key true, whereas '!key=' makes key false
    if ee == '':     # missing '='
        val = True
    elif val == '':  # empty val
        val = False
    # treat the debug flag specially
    if key == 'debug':
        if val == False:
            val = 0
        elif val == True:
            val = 1
        else:
            try:
                val = int(val)
                if val < 0:
                    val = 0
            except:
                # deathLNO('improper debug flag value')
                raise Exception('improper debug flag value')
    flags[key] = val
    # print(flags)

def getFlag(s):
    global flags
    if s in flags:
        return flags[s]
    else:
        return None

def death(msg):
    print(msg, file=sys.stderr)
    exit(1)

def deathLNO(msg):
    global Lno, Fname, Line
    print('%4d [%s]: %s' % (Lno, Fname, msg), file=sys.stderr)
    print('line:', Line, file=sys.stderr)
    exit(1)

def push(struct, item):
    struct.append(item)

def defang(exp):
    # if exp is of the form '<xxx>', return xxx
    # otherwise leave alone
    match = re.match('<(.+)>$', exp)
    if match:
        return match.group(1)
    return exp

def defangg(item):
    """
    item format      returns
    -----------      -------
    PQR              (PQR, None)
    <pqr>            (pqr, pqr)
    <PQR>            (PQR, pqr)  # pqr is PQR in lowercase
    <pqr>stu         (pqr, stu)
    <PQR>stu         (PQR, stu)
                     death in any other cases
    pqr is a nonterm and PQR is a term (token).
    The first item in the returned tuple is either a Nonterm or a Term
    The second item in the tuple is either None or an identifier starting in lowercase
    """
    tnt = None
    field = None
    debug('[defangg] item=%s' % item)
    m = re.match(r'<(\w+)>(.*)$', item)
    if m:
        tnt = m.group(1)
        field = m.group(2)
        if field == '':
            if isTerm(tnt):
                field = tnt.lower()
            else:
                field = tnt
    else:
        m = re.match('\w+$', item)
        if m:
            tnt = item
            field = None
    # just check for legal values (done once)
    if tnt == None or tnt == '':
        deathLNO('malformed RHS grammar item %s' % item)
    if not isTerm(tnt) and not isNonterm(tnt):
        deathLNO('malformed RHS grammar item %s' % item)
    if isTerm(tnt) and not tnt in term:
        deathLNO('unknown token name in RHS grammar item %s' % item)
    if field == None:
        if not isTerm(tnt):
            deathLNO('cannot have a bare nonterm in RHS grammar item %s' % item)
    elif not isID(field):
        deathLNO('field %s is an invalid identifier in RHS grammar item %s' % (field, item))
    return (tnt, field)

def isID(item):
    return re.match('[a-z]\w*$', item)

def isNonterm(nt):
    debug('[isNonterm] nt=%s' % nt)
    if nt == 'void' or len(nt) == 0:
        return False
    return re.match('[a-z]\w*$', nt)

def isClass(cls):
    return cls == 'void' or re.match('[A-Z][\$\w]*$', cls)

def isTerm(term):
    return re.match('[A-Z][A-Z\d]*$', term)

def nt2cls(nt):
    # return the class name of the nonterminal nt
    return nt[0].upper() + nt[1:]

if __name__ == '__main__':
    main()
