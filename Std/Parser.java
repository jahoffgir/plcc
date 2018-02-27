import java.util.*;
import java.io.*;

// parses the strings given on the command line
// and prints their results
public class Parser {

    public Scan scn; // scanner object

    public Parser(BufferedReader rdr) {
        scn = new Scan(rdr);
    }

    public static void main(String [] args) {
	Trace trace = null;
        for (int i=0 ; i<args.length ; i++) {
            String s = args[i];
            if (s.equals("-t") && trace == null) {
                trace = new Trace();
                continue;
            }
            Scan scn;
            scn = new Scan(new BufferedReader(new StringReader(s)));
            System.out.print(s + " -> ");
            try {
		if (trace != null) {
		    trace.reset();
                    System.out.println();
                }
                System.out.println(PLCC$Start.parse(scn, trace));
            } catch (NullPointerException e) {
                System.out.println("Premature end of input");
            } catch (Exception e) {
		System.out.println(e);
            } 
        }
    }
}
