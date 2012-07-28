import lxml.etree
import glob
import sys
import re
import Bcfg2.Server.Admin
import Bcfg2.Options
from Bcfg2.Server.Plugins.Metadata import MetadataConsistencyError


class Bundle(Bcfg2.Server.Admin.MetadataCore):
    __shorthelp__ = "List and view bundle entries"
    __longhelp__ = (__shorthelp__ + "\n\nbcfg2-admin bundle list-xml"
                                    "\nbcfg2-admin bundle list-genshi"
                                    "\nbcfg2-admin bundle show\n")
    __usage__ = ("bcfg2-admin bundle [options] [list-xml|list-genshi|show]")

    def __call__(self, args):
        Bcfg2.Server.Admin.MetadataCore.__call__(self, args)
        rg = re.compile(r'([^.]+\.(?:[a-z][a-z\-]+))(?![\w\.])',
                        re.IGNORECASE | re.DOTALL)

        # Get all bundles out of the Bundle/ directory
        repo = self.setup['repo']
        xml_list = glob.glob("%s/Bundler/*.xml" % repo)
        genshi_list = glob.glob("%s/Bundler/*.genshi" % repo)

        if len(args) == 0:
            self.errExit("No argument specified.\n"
                         "Please see bcfg2-admin bundle help for usage.")
        # Lists all available xml bundles
        elif args[0] in ['list-xml', 'ls-xml']:
            bundle_name = []
            for bundle_path in xml_list:
                bundle_name.append(rg.search(bundle_path).group(1))
            for bundle in bundle_name:
                print(bundle.split('.')[0])
        # Lists all available genshi bundles
        elif args[0] in ['list-genshi', 'ls-gen']:
            bundle_name = []
            for bundle_path in genshi_list:
                bundle_name.append(rg.search(bundle_path).group(1))
            for bundle in bundle_name:
                print(bundle.split('.')[0])
        # Shows a list of all available bundles and prints bundle
        # details after the user choose one bundle.
        # FIXME: Add support for detailed output of genshi bundles
        # FIXME: This functionality is almost identical with
        #        bcfg2-info bundles
        elif args[0] in ['show']:
            bundle_name = []
            bundle_list = xml_list + genshi_list
            for bundle_path in bundle_list:
                print "matching %s" % bundle_path
                bundle_name.append(rg.search(bundle_path).group(1))
            text = "Available bundles (Number of bundles: %s)" % \
                    (len(bundle_list))
            print(text)
            print("%s" % (len(text) * "-"))
            for i in range(len(bundle_list)):
                print("[%i]\t%s" % (i, bundle_name[i]))
            try:
                lineno = raw_input("Enter the line number of a bundle for details: ")
            except NameError:
                lineno = input("Enter the line number of a bundle for details: ")
            if int(lineno) >= int(len(bundle_list)):
                print("No line with this number.")
            else:
                if '%s/Bundler/%s' % \
                            (repo, bundle_name[int(lineno)]) in genshi_list:
                    print("Detailed output for *.genshi bundles is not supported.")
                else:
                    print('Details for the "%s" bundle:' % \
                            (bundle_name[int(lineno)].split('.')[0]))
                    tree = lxml.etree.parse(bundle_list[int(lineno)])
                    #Prints bundle content
                    #print(lxml.etree.tostring(tree))
                    names = ['Action', 'Package', 'Path', 'Service']
                    for name in names:
                        for node in tree.findall("//" + name):
                            print("%s:\t%s" % (name, node.attrib["name"]))
        else:
            print("No command specified")
            raise SystemExit(1)
